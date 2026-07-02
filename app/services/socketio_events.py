from flask_socketio import emit, join_room, leave_room
from flask import session, request
from app import socketio, db
from app.models import User, Appointment, MedicalHistory
from app.utils.auth import get_current_user
from app.utils.timezone import pkt_now_naive
from datetime import datetime
import json

@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    user = get_current_user()
    if user:
        print(f'User {user.name} connected')
        emit('status', {'msg': f'Welcome, {user.name}!', 'type': 'success'})
    else:
        print('Anonymous user connected')
        emit('status', {'msg': 'Please log in to use chat', 'type': 'warning'})

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    user = get_current_user()
    if user:
        print(f'User {user.name} disconnected')

@socketio.on('start_call')
def handle_start_call(data):
    """Handle doctor starting the call - signals patient to join AND persists state"""
    user = get_current_user()
    if not user or user.role != 'doctor':
        emit('error', {'msg': 'Only doctors can start calls'})
        return
    
    appointment_id = data.get('appointment_id')
    if not appointment_id:
        emit('error', {'msg': 'Appointment ID required'})
        return
        
    # Verify appointment access
    appointment = Appointment.query.get(appointment_id)
    if not appointment or appointment.doctor.user_id != user.id:
        emit('error', {'msg': 'Access denied'})
        return
    
    # PERSIST STATE: Mark call as active in database (for late-joining patients)
    appointment.is_call_active = True
    appointment.call_started_at = pkt_now_naive()
    if not appointment.doctor_joined_video:
        appointment.doctor_joined_video = True
        appointment.doctor_joined_at = pkt_now_naive()
    db.session.commit()
    
    # Emit to the room that the call has started
    room = f'appointment_{appointment_id}'
    emit('call_started', {
        'appointment_id': appointment_id,
        'doctor_name': user.name,
        'timestamp': datetime.now().isoformat()
    }, room=room)
    
    print(f'Doctor {user.name} started call for appointment {appointment_id} (State persisted)')

@socketio.on('end_call')
def handle_end_call(data):
    """Handle call ending - resets call state in database"""
    user = get_current_user()
    if not user:
        emit('error', {'msg': 'Authentication required'})
        return
    
    appointment_id = data.get('appointment_id')
    if not appointment_id:
        emit('error', {'msg': 'Appointment ID required'})
        return
        
    # Verify appointment access (both patient and doctor can end)
    appointment = Appointment.query.get(appointment_id)
    if not appointment:
        emit('error', {'msg': 'Appointment not found'})
        return
    
    # Check if user is part of this appointment
    if user.role == 'doctor' and appointment.doctor.user_id != user.id:
        emit('error', {'msg': 'Access denied'})
        return
    elif user.role == 'patient' and appointment.patient.user_id != user.id:
        emit('error', {'msg': 'Access denied'})
        return
    
    # Reset call state (clear mutual timer AFTER evaluating 3-minute prescription gate)
    from app.utils.prescription_gate import try_unlock_prescription_from_mutual_video

    try_unlock_prescription_from_mutual_video(appointment)
    appointment.is_call_active = False
    if appointment.prescription_unlocked:
        appointment.mutual_call_start = None
    db.session.commit()
    
    # ─── RECORDING: Stop when either party ends call (next mutual will start new) ───
    try:
        from app.services.recording_service import stop_recording
        stop_recording(appointment_id)
    except Exception:
        pass  # Never let recording affect main flow
    
    # Notify the room
    room = f'appointment_{appointment_id}'
    emit('call_ended', {
        'appointment_id': appointment_id,
        'ended_by': user.role,
        'timestamp': datetime.now().isoformat()
    }, room=room)
    
    print(f'{user.role.capitalize()} {user.name} ended call for appointment {appointment_id}')


@socketio.on('join_appointment_room')
def handle_join_appointment_room(data):
    """Join a specific appointment chat room"""
    user = get_current_user()
    if not user:
        emit('error', {'msg': 'Authentication required'})
        return
    
    appointment_id = data.get('appointment_id')
    if not appointment_id:
        emit('error', {'msg': 'Appointment ID required'})
        return
    
    # Verify user has access to this appointment
    appointment = Appointment.query.get(appointment_id)
    if not appointment:
        emit('error', {'msg': 'Appointment not found'})
        return
    
    # Check if user is either the doctor or patient for this appointment
    has_access = False
    if user.role == 'doctor' and appointment.doctor.user_id == user.id:
        has_access = True
    elif user.role == 'patient' and appointment.patient.user_id == user.id:
        has_access = True
    
    if not has_access:
        emit('error', {'msg': 'Access denied to this appointment'})
        return
    
    # Check if appointment is approved or completed (completed allows read-only access)
    if appointment.status not in ['approved', 'completed']:
        emit('error', {'msg': 'Chat is only available for approved or completed appointments'})
        return
    
    # For patients: check if payment is approved (patients must complete payment before chatting)
    if user.role == 'patient' and appointment.payment_status != 'approved':
        emit('error', {'msg': 'Please complete payment approval before accessing chat'})
        return
    
    # Join the appointment room (default namespace)
    room = f'appointment_{appointment_id}'
    join_room(room)
    
    # Store room info in session
    session['current_room'] = room
    session['appointment_id'] = appointment_id
    
    emit('status', {'msg': f'Joined appointment chat room', 'type': 'success'})
    print(f'[CHAT] {user.name} joined room {room}')
    
    # Load chat history
    load_chat_history(appointment_id)

@socketio.on('leave_appointment_room')
def handle_leave_appointment_room():
    """Leave the current appointment chat room"""
    room = session.get('current_room')
    if room:
        leave_room(room)
        session.pop('current_room', None)
        session.pop('appointment_id', None)
        emit('status', {'msg': 'Left chat room', 'type': 'info'})

@socketio.on('send_message')
def handle_send_message(data):
    """Handle sending a message in appointment chat"""
    user = get_current_user()
    if not user:
        emit('error', {'msg': 'Authentication required'})
        return

    # Use appointment_id from payload first — avoids multi-socket session confusion.
    # view.html also creates a socket + sets session['appointment_id'], so we can't
    # reliably trust the session on the chat page's socket. The frontend now sends
    # appointment_id in the payload making this fully self-contained.
    appointment_id = data.get('appointment_id') or session.get('appointment_id')
    if not appointment_id:
        emit('error', {'msg': 'No active appointment room'})
        return

    message_text = data.get('message', '').strip()
    if not message_text:
        emit('error', {'msg': 'Message cannot be empty'})
        return

    # Verify appointment access
    appointment = Appointment.query.get(appointment_id)
    if not appointment:
        emit('error', {'msg': 'Appointment not found'})
        return

    # Check if appointment is approved (can't send new messages if completed/cancelled)
    if appointment.status != 'approved':
        emit('error', {'msg': 'You cannot send messages for completed or cancelled appointments. Chat is read-only.'})
        return

    # For patients: check payment status
    if user.role == 'patient' and appointment.payment_status != 'approved':
        emit('error', {'msg': 'Payment must be approved before chatting'})
        return

    # Check access
    has_access = False
    if user.role == 'doctor' and appointment.doctor.user_id == user.id:
        has_access = True
    elif user.role == 'patient' and appointment.patient.user_id == user.id:
        has_access = True

    if not has_access:
        emit('error', {'msg': 'Access denied'})
        return
    
    # Create message data
    message_data = {
        'id': f'msg_{datetime.now().timestamp()}',
        'user_id': user.id,
        'user_name': user.name,
        'user_role': user.role,
        'message': message_text,
        'timestamp': datetime.now().isoformat(),
        'appointment_id': appointment_id
    }
    
    # Save to medical history chat logs
    medical_history = MedicalHistory.query.filter_by(appointment_id=appointment_id).first()
    if not medical_history:
        # Create medical history entry if it doesn't exist
        medical_history = MedicalHistory(
            patient_id=appointment.patient_id,
            doctor_id=appointment.doctor_id,
            appointment_id=appointment_id,
            disease=appointment.disease_category,
            chat_logs=[]
        )
        db.session.add(medical_history)
    
    # Add message to chat logs
    import json
    chat_logs = medical_history.chat_logs
    if isinstance(chat_logs, str):
        try:
            chat_logs = json.loads(chat_logs)
        except:
            chat_logs = []
    
    logs = list(chat_logs or [])
    logs.append(message_data)
    
    # Re-assign AND use flag_modified to guarantee SQLAlchemy detects the JSON change
    medical_history.chat_logs = logs
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(medical_history, 'chat_logs')
    medical_history.updated_at = datetime.utcnow()
    
    try:
        db.session.commit()
        
        # ─── Track doctor chat (analytics / history only). Prescription unlock is video-only — see /video/check-unlock. ───
        if user.role == 'doctor' and not appointment.doctor_sent_chat:
            appointment.doctor_sent_chat = True
            db.session.commit()
        
        # Broadcast to room (default namespace)
        room = f'appointment_{appointment_id}'
        print(f"[CHAT] Broadcasting new_message to room: {room}")
        socketio.emit('new_message', message_data, room=room)
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        db.session.rollback()
        emit('error', {'msg': f'Failed to send message: {str(e)}'})
        print(f'Error sending message: {e}')

@socketio.on('send_prescription')
def handle_send_prescription(data):
    """Handle sending prescription from doctor"""
    user = get_current_user()
    if not user or user.role != 'doctor':
        emit('error', {'msg': 'Only doctors can send prescriptions'})
        return
    
    appointment_id = session.get('appointment_id')
    if not appointment_id:
        emit('error', {'msg': 'No active appointment room'})
        return
    
    prescription_text = data.get('prescription', '').strip()
    if not prescription_text:
        emit('error', {'msg': 'Prescription cannot be empty'})
        return
    
    # Verify appointment access
    appointment = Appointment.query.get(appointment_id)
    if not appointment or appointment.doctor.user_id != user.id:
        emit('error', {'msg': 'Access denied'})
        return
    
    # Check if appointment is approved (can't send prescriptions if completed)
    if appointment.status != 'approved':
        emit('error', {'msg': 'Cannot send prescriptions for completed or cancelled appointments'})
        return
    
    # Update medical history with prescription
    medical_history = MedicalHistory.query.filter_by(appointment_id=appointment_id).first()
    if not medical_history:
        medical_history = MedicalHistory(
            patient_id=appointment.patient_id,
            doctor_id=appointment.doctor_id,
            appointment_id=appointment_id,
            disease=appointment.disease_category,
            chat_logs=[]
        )
        db.session.add(medical_history)
    
    medical_history.prescription = prescription_text
    medical_history.updated_at = datetime.utcnow()
    
    # Add prescription message to chat
    prescription_message = {
        'id': f'prescription_{datetime.now().timestamp()}',
        'user_id': user.id,
        'user_name': user.name,
        'user_role': user.role,
        'message': f'Prescription: {prescription_text}',
        'timestamp': datetime.now().isoformat(),
        'appointment_id': appointment_id,
        'type': 'prescription'
    }
    
    if not medical_history.chat_logs:
        medical_history.chat_logs = []
    
    medical_history.chat_logs.append(prescription_message)
    
    try:
        db.session.commit()
        
        # Emit prescription to room (default namespace)
        room = f'appointment_{appointment_id}'
        socketio.emit('new_message', prescription_message, room=room)
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        db.session.rollback()
        emit('error', {'msg': f'Failed to send prescription: {str(e)}'})
        print(f'Error sending prescription: {e}')

@socketio.on('typing')
def handle_typing(data):
    """Handle typing indicators"""
    user = get_current_user()
    if not user:
        return
    
    appointment_id = session.get('appointment_id')
    if not appointment_id:
        return
    
    room = f'appointment_{appointment_id}'
    typing_data = {
        'user_id': user.id,
        'user_name': user.name,
        'user_role': user.role,
        'is_typing': data.get('is_typing', False)
    }
    
    emit('user_typing', typing_data, room=room, include_self=False)

def load_chat_history(appointment_id):
    """Load chat history for an appointment and send only to the requesting client"""
    medical_history = MedicalHistory.query.filter_by(appointment_id=appointment_id).first()
    
    messages = []
    if medical_history and medical_history.chat_logs:
        messages = medical_history.chat_logs
    
    # Parse JSON if needed
    import json
    if isinstance(messages, str):
        try:
            messages = json.loads(messages)
        except:
            messages = []
            
    # Send ONLY to the user who just joined (not the whole room)
    socketio.emit('chat_history', {
        'messages': messages,
        'appointment_id': appointment_id
    }, to=request.sid)


@socketio.on('get_appointment_status')
def handle_get_appointment_status():
    """Get current appointment status"""
    user = get_current_user()
    if not user:
        emit('error', {'msg': 'Authentication required'})
        return
    
    appointment_id = session.get('appointment_id')
    if not appointment_id:
        emit('error', {'msg': 'No active appointment'})
        return
    
    appointment = Appointment.query.get(appointment_id)
    if not appointment:
        emit('error', {'msg': 'Appointment not found'})
        return
    
    # Check access
    has_access = False
    if user.role == 'doctor' and appointment.doctor.user_id == user.id:
        has_access = True
    elif user.role == 'patient' and appointment.patient.user_id == user.id:
        has_access = True
    
    if not has_access:
        emit('error', {'msg': 'Access denied'})
        return
    
    emit('appointment_status', {
        'appointment_id': appointment.id,
        'status': appointment.status,
        'appointment_date': appointment.appointment_date.isoformat(),
        'appointment_time': appointment.appointment_time.isoformat(),
        'disease_category': appointment.disease_category,
        'patient_name': appointment.patient.user.name if user.role == 'doctor' else None,
        'doctor_name': appointment.doctor.user.name if user.role == 'patient' else None
    })
