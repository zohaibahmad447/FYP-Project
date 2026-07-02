from datetime import datetime, timedelta

from flask import Blueprint, render_template, request, jsonify, session, current_app
from app.models import Question, Answer, AnswerReply, AnswerHelpfulVote, AnswerNotHelpfulVote, QuestionBookmark
from app.database import db
from app.utils.auth import get_current_user
from app.models import QuestionView
from app.utils.categories import normalize_category
from app.services.ai_chatbot_service import AIChatbotService
from app.utils.file_upload import save_uploaded_file
from sqlalchemy import func, or_

qa_bp = Blueprint('qa', __name__)


def _ai_rate_limited() -> bool:
    """Simple per-session limiter for AI endpoint abuse prevention."""
    now = datetime.utcnow()
    window_minutes = 10
    max_requests = 20

    timestamps = session.get('qa_ai_chat_timestamps', [])
    cleaned = []
    for iso_ts in timestamps:
        try:
            ts = datetime.fromisoformat(iso_ts)
            if now - ts <= timedelta(minutes=window_minutes):
                cleaned.append(iso_ts)
        except ValueError:
            continue

    if len(cleaned) >= max_requests:
        session['qa_ai_chat_timestamps'] = cleaned
        return True

    cleaned.append(now.isoformat())
    session['qa_ai_chat_timestamps'] = cleaned
    return False


def _can_user_reply_on_answer(user, answer) -> bool:
    """Allow question owner and approved doctors to post in answer thread.

    Doctors who have already posted an answer on the question cannot post
    additional thread replies (single-response policy).
    """
    if not user or not answer or not answer.question:
        return False

    if user.role == 'patient' and user.patient_profile:
        return user.patient_profile.id == answer.question.patient_id

    if user.role == 'doctor' and user.doctor_profile:
        doctor = user.doctor_profile
        if not (doctor.is_approved and doctor.is_verified):
            return False

        existing_answer = Answer.query.filter_by(
            question_id=answer.question.id,
            doctor_id=doctor.id,
            is_deleted=False
        ).first()

        # If doctor has already answered this question, block extra replies.
        return existing_answer is None

    return False


@qa_bp.route('/')
def index():
    """Q&A listing page"""
    page = request.args.get('page', 1, type=int)
    category = request.args.get('category', 'all')
    answered = request.args.get('answered', 'all')
    search = request.args.get('search', '').strip()
    
    query = Question.query.filter_by(is_deleted=False)

    if search:
        like_term = f"%{search}%"
        query = query.filter(
            or_(
                Question.title.ilike(like_term),
                Question.content.ilike(like_term)
            )
        )
    
    if category != 'all':
        query = query.filter_by(category=category)
    
    if answered == 'answered':
        query = query.filter_by(is_answered=True)
    elif answered == 'unanswered':
        query = query.filter_by(is_answered=False)
    
    questions = query.order_by(
        func.coalesce(Question.last_activity_at, Question.created_at).desc()
    ).paginate(
        page=page, per_page=6, error_out=False
    )
    
    # Get categories for filter (with count)
    categories_with_count = db.session.query(
        Question.category,
        func.count(Question.id).label('count')
    ).filter_by(
        is_deleted=False
    ).group_by(Question.category).all()
    
    # Get all medical categories for reference
    from app.utils.categories import get_all_categories
    all_categories = get_all_categories()
    
    return render_template('qa/index.html',
                         questions=questions,
                         categories=categories_with_count,
                         all_categories=all_categories,
                         current_category=category,
                         current_answered=answered,
                         current_search=search)


@qa_bp.route('/ai-chat', methods=['POST'])
def ai_chat():
    """Role-aware AI assistant endpoint with privacy guardrails."""
    if _ai_rate_limited():
        return jsonify({
            'success': False,
            'message': 'Too many requests. Please wait a moment and try again.'
        }), 429

    user = get_current_user()

    payload = request.get_json(silent=True) or {}
    message = (payload.get('message') or '').strip()
    history = payload.get('history') or []
    recommendation_gate = payload.get('recommendation_gate')

    if not message:
        return jsonify({'success': False, 'message': 'Message is required.'}), 400

    result = AIChatbotService.answer(
        user=user,
        message=message,
        history=history,
        recommendation_gate=recommendation_gate,
    )
    if not result.get('ok'):
        return jsonify({'success': False, 'message': result.get('error', 'Unable to process request.')}), 400

    return jsonify({
        'success': True,
        'reply': result.get('reply', ''),
        'recommendations': result.get('recommendations', []),
        'specialty': result.get('specialty'),
        'llm_provider': result.get('llm_provider'),
        'recommendation_gate': result.get('recommendation_gate'),
    })

@qa_bp.route('/question/<int:question_id>')
def view_question(question_id):
    """View individual question and answers"""
    question = Question.query.filter_by(
        id=question_id,
        is_deleted=False
    ).first_or_404()

    user = get_current_user()
    is_admin = bool(user and user.role == 'admin')

    # Increment only once per user (persisted) and never for admins.
    if user and not is_admin:
        existing_view = QuestionView.query.filter_by(
            question_id=question_id,
            user_id=user.id
        ).first()

        if not existing_view:
            db.session.add(QuestionView(question_id=question_id, user_id=user.id))
            db.session.query(Question).filter_by(id=question_id).update({
                Question.view_count: func.coalesce(Question.view_count, 0) + 1
            })
            db.session.commit()
            db.session.refresh(question)
    
    # Get answers for this question
    answers = Answer.query.filter_by(
        question_id=question_id,
        is_deleted=False
    ).order_by(Answer.created_at.asc()).all()

    user = get_current_user()

    answer_replies = {}
    can_reply_on_answers = {}
    answer_reply_targets = []
    if answers:
        answer_ids = [answer.id for answer in answers]
        answer_doctor_user_map = {answer.id: answer.doctor.user_id for answer in answers}
        reply_rows = AnswerReply.query.filter(
            AnswerReply.answer_id.in_(answer_ids),
            AnswerReply.is_deleted.is_(False)
        ).order_by(AnswerReply.created_at.asc()).all()

        for answer in answers:
            answer_replies[answer.id] = []
            can_reply_on_answers[answer.id] = _can_user_reply_on_answer(user, answer)
            if can_reply_on_answers[answer.id]:
                answer_reply_targets.append(answer)

        for reply in reply_rows:
            doctor_user_id = answer_doctor_user_map.get(reply.answer_id)
            # Legacy cleanup at read-time: do not show doctor self-replies
            # under their own answer card.
            if doctor_user_id and reply.user_id == doctor_user_id:
                continue
            answer_replies.setdefault(reply.answer_id, []).append(reply)

    answer_feedback_status = {}
    if answers:
        answer_ids = [answer.id for answer in answers]

        helpful_votes = AnswerHelpfulVote.query.filter(
            AnswerHelpfulVote.patient_id == question.patient_id,
            AnswerHelpfulVote.answer_id.in_(answer_ids)
        ).all()
        not_helpful_votes = AnswerNotHelpfulVote.query.filter(
            AnswerNotHelpfulVote.patient_id == question.patient_id,
            AnswerNotHelpfulVote.answer_id.in_(answer_ids)
        ).all()

        helpful_by_answer = {vote.answer_id: vote for vote in helpful_votes}
        not_helpful_by_answer = {vote.answer_id: vote for vote in not_helpful_votes}

        for answer in answers:
            helpful_vote = helpful_by_answer.get(answer.id)
            not_helpful_vote = not_helpful_by_answer.get(answer.id)

            if helpful_vote and not not_helpful_vote:
                answer_feedback_status[answer.id] = 'satisfied'
            elif not_helpful_vote and not helpful_vote:
                answer_feedback_status[answer.id] = 'not_satisfied'
            elif helpful_vote and not_helpful_vote:
                answer_feedback_status[answer.id] = (
                    'satisfied'
                    if helpful_vote.created_at >= not_helpful_vote.created_at
                    else 'not_satisfied'
                )
            else:
                answer_feedback_status[answer.id] = 'unrated'
    
    # Check if current user (if logged in) can answer this question
    can_answer = False
    can_vote_on_answers = bool(
        user
        and user.role == 'patient'
        and user.patient_profile
        and user.patient_profile.id == question.patient_id
    )
    if user and user.role == 'doctor' and user.doctor_profile:
        doctor = user.doctor_profile
        if doctor.is_approved and doctor.is_verified:
            doctor_category = normalize_category(doctor.category)
            question_category = normalize_category(question.category)
            can_answer = (doctor_category.lower() == question_category.lower())

    is_bookmarked = False
    if user and user.role == 'patient' and user.patient_profile:
        is_bookmarked = QuestionBookmark.query.filter_by(
            question_id=question.id,
            patient_id=user.patient_profile.id
        ).first() is not None

    related_questions = Question.query.filter(
        Question.is_deleted.is_(False),
        Question.id != question.id,
        Question.category == question.category
    ).order_by(
        func.coalesce(Question.last_activity_at, Question.created_at).desc()
    ).limit(5).all()
    
    return render_template('qa/view_question.html',
                         question=question,
                         answers=answers,
                         can_answer=can_answer,
                         is_bookmarked=is_bookmarked,
                         related_questions=related_questions,
                         can_vote_on_answers=can_vote_on_answers,
                         can_post_any_reply=any(can_reply_on_answers.values()) if can_reply_on_answers else False,
                         answer_reply_targets=answer_reply_targets,
                         can_reply_on_answers=can_reply_on_answers,
                         answer_replies=answer_replies,
                         answer_feedback_status=answer_feedback_status)


@qa_bp.route('/question/<int:question_id>/bookmark', methods=['POST'])
def toggle_bookmark(question_id):
    """Toggle bookmark for patient users."""
    user = get_current_user()
    if not user or user.role != 'patient' or not user.patient_profile:
        return jsonify({'success': False, 'message': 'Please login as a patient.'}), 403

    question = Question.query.filter_by(id=question_id, is_deleted=False).first_or_404()
    bookmark = QuestionBookmark.query.filter_by(
        question_id=question.id,
        patient_id=user.patient_profile.id
    ).first()

    if bookmark:
        db.session.delete(bookmark)
        is_bookmarked = False
    else:
        bookmark = QuestionBookmark(
            question_id=question.id,
            patient_id=user.patient_profile.id
        )
        db.session.add(bookmark)
        is_bookmarked = True

    db.session.commit()

    return jsonify({
        'success': True,
        'bookmarked': is_bookmarked,
        'bookmark_count': question.bookmarks.count()
    })


@qa_bp.route('/answer/<int:answer_id>/reply', methods=['POST'])
def reply_to_answer(answer_id):
    """Post follow-up reply in answer thread.

        Policy:
        - Question owner patient can reply.
        - Approved doctors can reply only if they have not already answered
            this question.
        - Others can read but cannot write.
    """
    user = get_current_user()
    if not user:
        return jsonify({'success': False, 'message': 'Please login to reply.'}), 403

    answer = Answer.query.filter_by(id=answer_id, is_deleted=False).first_or_404()
    if not _can_user_reply_on_answer(user, answer):
        return jsonify({
            'success': False,
            'message': 'Only doctors and the post owner can reply in this thread.'
        }), 403

    content = (request.form.get('content') or '').strip()
    if not content:
        return jsonify({'success': False, 'message': 'Reply content cannot be empty.'}), 400

    photo_path = None
    photo_file = request.files.get('photo')
    if photo_file and photo_file.filename:
        success, file_path, error = save_uploaded_file(
            photo_file,
            current_app.config.get('UPLOAD_FOLDER', 'app/static/uploads'),
            'qa_replies'
        )
        if not success:
            return jsonify({'success': False, 'message': error or 'Unable to upload photo.'}), 400
        photo_path = file_path

    reply = AnswerReply(
        answer_id=answer.id,
        user_id=user.id,
        content=content,
        photo_path=photo_path,
        is_deleted=False
    )

    answer.question.last_activity_at = datetime.utcnow()
    db.session.add(reply)
    db.session.commit()

    role_label = 'Doctor' if user.role == 'doctor' else 'Question Owner'

    return jsonify({
        'success': True,
        'reply': {
            'id': reply.id,
            'answer_id': reply.answer_id,
            'author_name': user.name,
            'author_role': role_label,
            'created_at': reply.created_at.strftime('%b %d, %Y %I:%M %p'),
            'content': reply.content,
            'photo_url': f"/static/uploads/{reply.photo_path}" if reply.photo_path else None
        }
    })


@qa_bp.route('/answer/<int:answer_id>/helpful', methods=['POST'])
def toggle_helpful_vote(answer_id):
    """Toggle helpful vote for patient users."""
    user = get_current_user()
    if not user or user.role != 'patient' or not user.patient_profile:
        return jsonify({'success': False, 'message': 'Please login as a patient.'}), 403

    answer = Answer.query.filter_by(id=answer_id, is_deleted=False).first_or_404()
    if not answer.question or answer.question.patient_id != user.patient_profile.id:
        return jsonify({'success': False, 'message': 'Only the question owner can rate answers.'}), 403

    vote = AnswerHelpfulVote.query.filter_by(
        answer_id=answer.id,
        patient_id=user.patient_profile.id
    ).first()

    if vote:
        db.session.delete(vote)
        is_helpful = False
    else:
        existing_not_helpful = AnswerNotHelpfulVote.query.filter_by(
            answer_id=answer.id,
            patient_id=user.patient_profile.id
        ).first()
        if existing_not_helpful:
            db.session.delete(existing_not_helpful)

        vote = AnswerHelpfulVote(
            answer_id=answer.id,
            patient_id=user.patient_profile.id
        )
        db.session.add(vote)
        is_helpful = True

    db.session.commit()

    return jsonify({
        'success': True,
        'helpful': is_helpful,
        'helpful_count': answer.helpful_count,
        'not_helpful_count': answer.not_helpful_count
    })


@qa_bp.route('/answer/<int:answer_id>/not-helpful', methods=['POST'])
def toggle_not_helpful_vote(answer_id):
    """Toggle not helpful vote for patient users."""
    user = get_current_user()
    if not user or user.role != 'patient' or not user.patient_profile:
        return jsonify({'success': False, 'message': 'Please login as a patient.'}), 403

    answer = Answer.query.filter_by(id=answer_id, is_deleted=False).first_or_404()
    if not answer.question or answer.question.patient_id != user.patient_profile.id:
        return jsonify({'success': False, 'message': 'Only the question owner can rate answers.'}), 403

    vote = AnswerNotHelpfulVote.query.filter_by(
        answer_id=answer.id,
        patient_id=user.patient_profile.id
    ).first()

    if vote:
        db.session.delete(vote)
        is_not_helpful = False
    else:
        existing_helpful = AnswerHelpfulVote.query.filter_by(
            answer_id=answer.id,
            patient_id=user.patient_profile.id
        ).first()
        if existing_helpful:
            db.session.delete(existing_helpful)

        vote = AnswerNotHelpfulVote(
            answer_id=answer.id,
            patient_id=user.patient_profile.id
        )
        db.session.add(vote)
        is_not_helpful = True

    db.session.commit()

    return jsonify({
        'success': True,
        'not_helpful': is_not_helpful,
        'not_helpful_count': answer.not_helpful_count,
        'helpful_count': answer.helpful_count
    })
