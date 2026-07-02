import logging
import os
import re
from collections import defaultdict
from typing import Any, Dict, List, Optional

import requests
from sqlalchemy import func

from app.models import Appointment, Doctor, Patient, User
from app.utils.categories import get_all_categories, normalize_category


class AIChatbotService:
    """Role-aware AI assistant that uses Gemini with OpenRouter fallback and strict privacy boundaries."""

    GEMINI_MODEL = "gemini-1.5-flash"
    OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"

    # Keep assistant scope narrow and legal.
    BLOCKED_TOPICS = [
        "bomb", "weapon", "explosive", "kill", "murder", "terror", "suicide",
        "self harm", "hack", "malware", "phishing", "fraud", "fake id", "forgery",
        "adult content", "porn", "rape", "violence"
    ]

    GREETING_WORDS = {
        "hi", "hello", "hey", "salam", "assalam o alaikum", "assalamualaikum",
        "good morning", "good afternoon", "good evening"
    }

    SYMPTOM_SPECIALTY_MAP = {
        "chest pain": "Cardiology",
        "palpitations": "Cardiology",
        "high blood pressure": "Cardiology",
        "migraine": "Neurology",
        "headache": "Neurology",
        "seizure": "Neurology",
        "skin rash": "Dermatology",
        "acne": "Dermatology",
        "eczema": "Dermatology",
        "pregnancy": "Gynecology",
        "period": "Gynecology",
        "pcos": "Gynecology",
        "child fever": "Pediatrics",
        "baby": "Pediatrics",
        "joint pain": "Orthopedics",
        "back pain": "Orthopedics",
        "stomach pain": "Gastroenterology",
        "acidity": "Gastroenterology",
        "depression": "Psychiatry",
        "anxiety": "Psychiatry",
        "cough": "Pulmonology",
        "asthma": "Pulmonology",
        "kidney": "Nephrology",
        "urine": "Urology",
        "ear pain": "ENT",
        "throat": "ENT",
        "tooth": "Dentistry",
        "eye": "Ophthalmology",
        "diabetes": "Diabetology",
        "dizziness": "Neurology",
        "dizzy": "Neurology",
        "vertigo": "Neurology",
        "shortness of breath": "Pulmonology",
        "breathing problem": "Pulmonology",
        "breathing issue": "Pulmonology",
        "cannot breathe": "Pulmonology",
        "can't breathe": "Pulmonology",
        "out of breath": "Pulmonology",
        "breathless": "Pulmonology",
    }

    @classmethod
    def answer(
        cls,
        user: Optional[User],
        message: str,
        history: Optional[List[Dict]] = None,
        recommendation_gate: Any = None,
    ) -> Dict:
        message = (message or "").strip()
        history = history or []

        if not message:
            return {"ok": False, "error": "Please type a message.", "llm_provider": None}

        blocked_reason = cls._blocked_reason(message)
        if blocked_reason:
            return {
                "ok": True,
                "reply": (
                    "I can only help with legal healthcare and Quick Care platform topics. "
                    "I cannot assist with that request."
                ),
                "recommendations": [],
                "specialty": None,
                "guardrail": blocked_reason,
                "llm_provider": None,
                "recommendation_gate": None,
            }

        if cls._is_greeting_only(message):
            return {
                "ok": True,
                "reply": cls._greeting_reply(user),
                "recommendations": [],
                "specialty": None,
                "llm_provider": None,
                "recommendation_gate": None,
            }

        gate = cls._normalize_recommendation_gate(recommendation_gate)
        if gate.get("awaiting") and gate.get("specialty"):
            return cls._answer_recommendation_gate(
                message=message, gate=gate
            )

        if cls._is_likely_off_topic(message):
            return {
                "ok": True,
                "reply": (
                    "I can only help with health concerns, symptoms in general terms, and using Quick Care "
                    "(finding specialists, bookings, payments). Ask me something in that area and I will assist you."
                ),
                "recommendations": [],
                "specialty": None,
                "llm_provider": None,
                "recommendation_gate": None,
            }

        specialty = cls._infer_specialty(message)
        wants_immediate_listing = cls._wants_immediate_doctor_listing(message)
        symptom_triage = cls._is_symptom_triage_message(message)
        offer_gated_recs = bool(
            specialty and symptom_triage and not wants_immediate_listing
        )

        recommendations: List[Dict] = []
        if wants_immediate_listing and specialty:
            recommendations = cls._recommend_doctors(specialty=specialty, limit=5)
        elif wants_immediate_listing and not specialty:
            recommendations = []

        new_gate: Optional[Dict[str, Any]] = None
        defer_doctor_cards = offer_gated_recs

        if offer_gated_recs:
            new_gate = {"awaiting": True, "specialty": specialty}

        role_context = cls._role_context(user=user, user_message=message)
        doctor_context = cls._doctor_catalog_context(specialty=specialty, top_n=20)
        conversation_context = cls._compact_history(history)

        prompt = cls._build_prompt(
            user=user,
            user_message=message,
            role_context=role_context,
            doctor_context=doctor_context,
            recommendations=recommendations,
            specialty=specialty,
            history_text=conversation_context,
            defer_doctor_cards=defer_doctor_cards,
        )

        raw_llm = cls._call_gemini(prompt)
        llm_provider = None
        if raw_llm:
            llm_provider = "gemini"
        else:
            raw_llm = cls._call_openrouter(prompt)
            if raw_llm:
                llm_provider = "openrouter"

        if not raw_llm:
            final_reply = cls._fallback_reply(
                message=message,
                specialty=specialty,
                recommendations=recommendations,
                user_role=user.role if user else None,
                defer_doctor_cards=defer_doctor_cards,
            )
            llm_provider = "fallback"
        else:
            final_reply = cls._normalize_reply_text(raw_llm)

        if offer_gated_recs and new_gate:
            final_reply = cls._append_gated_offer(
                final_reply, specialty=new_gate["specialty"]
            )

        return {
            "ok": True,
            "reply": final_reply,
            "recommendations": recommendations,
            "specialty": specialty,
            "llm_provider": llm_provider,
            "recommendation_gate": new_gate,
        }

    @classmethod
    def _blocked_reason(cls, message: str) -> Optional[str]:
        lower = message.lower()
        for token in cls.BLOCKED_TOPICS:
            if token in lower:
                return token
        return None

    @classmethod
    def _normalize_recommendation_gate(cls, gate: Any) -> Dict[str, Any]:
        if not isinstance(gate, dict):
            return {}
        spec = gate.get("specialty")
        if isinstance(spec, str):
            spec = spec.strip() or None
        else:
            spec = None
        return {"awaiting": bool(gate.get("awaiting")), "specialty": spec}

    @classmethod
    def _parse_yes_no(cls, message: str) -> str:
        """Return 'yes', 'no', or 'unclear' for short consent replies."""
        raw = (message or "").strip().lower()
        raw = re.sub(r"[^\w\s]", " ", raw)
        raw = re.sub(r"\s+", " ", raw).strip()
        if not raw:
            return "unclear"

        yes_phrases = (
            "yes please",
            "yes go ahead",
            "go ahead",
            "sounds good",
            "sounds great",
            "show me",
            "show them",
            "please show",
            "ok show",
            "okay show",
        )
        no_phrases = (
            "no thanks",
            "no thank you",
            "not now",
            "rather not",
            "do not",
            "don't show",
            "dont show",
        )
        for p in yes_phrases:
            if raw == p or raw.startswith(p + " ") or raw.endswith(" " + p):
                return "yes"
        for p in no_phrases:
            if p in raw:
                return "no"

        tokens = raw.split()
        yes_tokens = {
            "yes",
            "yeah",
            "yep",
            "sure",
            "please",
            "ok",
            "okay",
            "y",
            "alright",
        }
        no_tokens = {"no", "nope", "nah", "not"}
        if len(tokens) <= 6:
            if any(t in yes_tokens for t in tokens) and not any(t in no_tokens for t in tokens):
                return "yes"
            if any(t in no_tokens for t in tokens) and not any(t in yes_tokens for t in tokens):
                return "no"
        return "unclear"

    @classmethod
    def _answer_recommendation_gate(
        cls,
        message: str,
        gate: Dict[str, Any],
    ) -> Dict:
        spec = gate.get("specialty")
        verdict = cls._parse_yes_no(message)

        if verdict == "yes" and spec:
            recs = cls._recommend_doctors(specialty=spec, limit=5)
            if not recs:
                reply = (
                    f"I could not find verified {spec} doctors on Quick Care with the current filters. "
                    "You can still use Find Doctors and adjust city or specialty."
                )
            else:
                reply = (
                    f"Here are a few verified {spec} specialists on Quick Care. "
                    "Tap a card to open a full profile and book when you are ready."
                )
            return {
                "ok": True,
                "reply": reply,
                "recommendations": recs,
                "specialty": spec,
                "llm_provider": None,
                "recommendation_gate": None,
            }

        if verdict == "no":
            return {
                "ok": True,
                "reply": (
                    "Understood. I will not show specialist profile cards. "
                    "Tell me more about how you feel, or ask about bookings, payments, or anything else on Quick Care."
                ),
                "recommendations": [],
                "specialty": spec,
                "llm_provider": None,
                "recommendation_gate": None,
            }

        return {
            "ok": True,
            "reply": (
                "Reply yes if you would like me to show verified specialist profiles on Quick Care, "
                "or no if you prefer to continue the conversation without listings."
            ),
            "recommendations": [],
            "specialty": spec,
            "llm_provider": None,
            "recommendation_gate": gate,
        }

    @classmethod
    def _looks_health_or_platform_related(cls, message: str) -> bool:
        lower = message.lower()
        platform_markers = (
            "quick care",
            "appointment",
            "booking",
            "book ",
            "cancel",
            "payment",
            "pay ",
            "invoice",
            "profile",
            "login",
            "password",
            "register",
            "prescription",
            "refund",
        )
        if any(p in lower for p in platform_markers):
            return True

        for category in get_all_categories():
            if category.lower() in lower:
                return True

        if normalize_category(message) in get_all_categories():
            return True

        for symptom_key in cls.SYMPTOM_SPECIALTY_MAP.keys():
            if symptom_key in lower:
                return True

        symptomish = (
            "pain",
            "ache",
            "hurt",
            "hurts",
            "fever",
            "cough",
            "rash",
            "bleed",
            "dizzy",
            "dizziness",
            "nausea",
            "vomit",
            "tired",
            "fatigue",
            "breath",
            "breathing",
            "swelling",
            "cramp",
            "itch",
            "symptom",
            "feel ill",
            "feeling",
            "experiencing",
            "unwell",
            "sick",
            "illness",
            "consult",
            "doctor",
            "specialist",
            "hospital",
            "clinic",
            "medicine",
            "tablet",
            "diagnosis",
            "treatment",
        )
        if any(s in lower for s in symptomish):
            return True

        body = (
            "head",
            "chest",
            "stomach",
            "abdomen",
            "back",
            "neck",
            "leg",
            "arm",
            "throat",
            "ear",
            "eye",
            "skin",
            "heart",
        )
        if any(re.search(rf"\b{b}\b", lower) for b in body):
            return True

        return False

    @classmethod
    def _is_likely_off_topic(cls, message: str) -> bool:
        if cls._looks_health_or_platform_related(message):
            return False
        lower = message.lower()
        chit_tokens = (
            "bmw",
            "mercedes",
            "ferrari",
            "tesla",
            "football",
            "cricket score",
            "movie",
            "netflix",
            "song",
            "joke",
            "poem",
            "recipe",
            "capital of",
            "who won",
            "stock price",
            "bitcoin",
        )
        if any(t in lower for t in chit_tokens):
            return True
        if re.search(r"\bdo you like\b", lower):
            return True
        if len(lower.split()) <= 8:
            return True
        return False

    @classmethod
    def _wants_immediate_doctor_listing(cls, message: str) -> bool:
        lower = message.lower()
        if re.search(r"\b(best|top|leading)\s+\w+ologists?\b", lower):
            return True
        if "find doctors" in lower or "find a doctor" in lower or "browse doctors" in lower:
            return True
        if "verified profile" in lower or "doctor near me" in lower or "doctors near" in lower:
            return True

        listing_verbs = ("show me", "list ", "list of", "open profiles", "profile links")
        doctor_terms = ("doctor", "doctors", "specialist", "specialists", "physician")
        if any(v in lower for v in listing_verbs) and any(d in lower for d in doctor_terms):
            return True
        return False

    @classmethod
    def _is_symptom_triage_message(cls, message: str) -> bool:
        lower = message.lower()
        for k in cls.SYMPTOM_SPECIALTY_MAP.keys():
            if k in lower:
                return True

        symptomish = (
            "pain",
            "ache",
            "hurt",
            "hurts",
            "fever",
            "cough",
            "rash",
            "bleed",
            "dizzy",
            "dizziness",
            "nausea",
            "vomit",
            "tired",
            "fatigue",
            "breath",
            "breathing",
            "swelling",
            "cramp",
            "itch",
            "symptom",
            "experiencing",
            "feel ",
            "feeling ",
            "i feel",
        )
        body = (
            "head",
            "chest",
            "stomach",
            "abdomen",
            "back",
            "neck",
            "leg",
            "arm",
            "throat",
            "ear",
            "eye",
            "skin",
            "heart",
        )
        hits = sum(1 for s in symptomish if s in lower)
        body_hits = sum(1 for b in body if re.search(rf"\b{b}\b", lower))
        if hits >= 1 and body_hits >= 1:
            return True
        if hits >= 2:
            return True
        if "feel" in lower and len(lower) > 40:
            return True
        return False

    @classmethod
    def _is_greeting_only(cls, message: str) -> bool:
        lower = re.sub(r"\s+", " ", message.lower().strip())
        if lower in cls.GREETING_WORDS:
            return True
        if len(lower) <= 5 and lower.isalpha():
            return lower in {"hi", "hey", "hello"}
        return False

    @staticmethod
    def _greeting_reply(user: Optional[User]) -> str:
        if not user:
            return (
                "Hello. I can help you find the right doctor, explain symptoms in simple terms, "
                "or guide you through Quick Care features. Tell me what you need."
            )

        if user.role == "doctor":
            return (
                "Hello doctor. I can help you review your patient trends, answer platform questions, "
                "or suggest follow-up care ideas for your own patients. What would you like to do?"
            )
        if user.role == "patient":
            return (
                "Hello. I can help you find the right doctor, explain symptoms, or guide you through "
                "your appointments and other Quick Care features. What can I help with?"
            )
        if user.role == "admin":
            return (
                "Hello. I can help with Quick Care platform guidance, doctor discovery, and safe "
                "high-level support questions. What do you need?"
            )
        return (
            "Hello. I can help you find the right doctor, explain symptoms, or answer Quick Care "
            "questions. What would you like to know?"
        )

    @staticmethod
    def _normalize_reply_text(text: str) -> str:
        cleaned = (text or "").strip()
        cleaned = re.sub(r"^#{1,6}\s*", "", cleaned, flags=re.MULTILINE)
        cleaned = cleaned.replace("**", "").replace("__", "")
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned

    @staticmethod
    def _append_gated_offer(reply: str, specialty: str) -> str:
        base = (reply or "").rstrip()
        tail = base.lower()
        if "reply yes" in tail and "profiles" in tail:
            return base
        plug = (
            f" If you would like, I can suggest a few verified {specialty.lower()} specialists on Quick Care. "
            "Reply yes to see profile cards here, or no to continue without listings."
        )
        return base + plug

    @classmethod
    def _infer_specialty(cls, message: str) -> Optional[str]:
        lower = message.lower().strip()

        if len(lower) < 4 or lower in cls.GREETING_WORDS:
            return None

        scores: Dict[str, float] = {}

        def add(cat: str, weight: float) -> None:
            scores[cat] = scores.get(cat, 0.0) + weight

        for category in get_all_categories():
            if category.lower() in lower:
                add(category, 12.0)

        normalized = normalize_category(message)
        if normalized in get_all_categories():
            add(normalized, 10.0)

        for symptom_key, category in cls.SYMPTOM_SPECIALTY_MAP.items():
            if symptom_key in lower:
                add(category, 4.0)

        cardio_markers = (
            "chest pain",
            "heart pain",
            "heart side",
            "pain on chest",
            "pain in chest",
            "pressure on chest",
            "tight chest",
            "palpitation",
            "irregular heartbeat",
            "radiating pain",
            "left arm pain",
        )
        c_hit = sum(1 for p in cardio_markers if p in lower)
        breath = any(
            t in lower
            for t in (
                "shortness of breath",
                "breathing issue",
                "breathing problem",
                "cannot breathe",
                "can't breathe",
                "out of breath",
                "breathless",
                "gasping",
                "trouble breathing",
                "difficulty breathing",
            )
        )
        heart_word = any(t in lower for t in ("heart", "cardiac"))
        chest_word = "chest" in lower
        dizzy = any(t in lower for t in ("dizziness", "dizzy", "vertigo", "lightheaded"))

        if c_hit:
            add("Cardiology", 8.0 + 2.0 * c_hit)
        if heart_word and breath:
            add("Cardiology", 10.0)
        if chest_word and breath:
            add("Cardiology", 9.0)
        if dizzy and (heart_word or chest_word) and breath:
            add("Cardiology", 8.0)
        elif dizzy and (heart_word or chest_word):
            add("Cardiology", 7.0)

        if not scores:
            return None

        best_cat, _best_score = max(scores.items(), key=lambda kv: kv[1])
        sc_card = scores.get("Cardiology", 0.0)
        sc_psych = scores.get("Psychiatry", 0.0)
        if sc_card and sc_psych and sc_card >= sc_psych - 1.5:
            if heart_word or chest_word or c_hit or (breath and dizzy):
                return "Cardiology"
        return best_cat

    @classmethod
    def _recommend_doctors(cls, specialty: Optional[str], limit: int = 5) -> List[Dict]:
        query = Doctor.query.filter(
            Doctor.is_approved.is_(True),
            Doctor.is_verified.is_(True),
        )

        if specialty:
            query = query.filter(func.lower(Doctor.category) == specialty.lower())

        doctors = query.order_by(Doctor.created_at.desc()).limit(60).all()

        ranked = sorted(
            doctors,
            key=lambda d: (
                d.average_rating if d.average_rating is not None else 0,
                d.review_count,
                d.experience or 0,
            ),
            reverse=True,
        )[:limit]

        results = []
        for d in ranked:
            results.append(
                {
                    "doctor_id": d.id,
                    "name": d.user.name,
                    "category": d.category,
                    "specialization": d.specialization,
                    "experience_years": d.experience,
                    "city": d.city,
                    "location": d.location,
                    "rating": d.average_rating,
                    "review_count": d.review_count,
                    "profile_url": f"/patients/doctor/{d.id}",
                }
            )
        return results

    @classmethod
    def _doctor_catalog_context(cls, specialty: Optional[str], top_n: int = 20) -> str:
        query = Doctor.query.filter(
            Doctor.is_approved.is_(True),
            Doctor.is_verified.is_(True),
        )
        if specialty:
            query = query.filter(func.lower(Doctor.category) == specialty.lower())

        doctors = query.order_by(Doctor.created_at.desc()).limit(top_n).all()
        lines = []
        for d in doctors:
            lines.append(
                f"- {d.user.name} | {d.category} | {d.specialization} | {d.city} | "
                f"{d.experience}y exp | rating {d.average_rating if d.average_rating is not None else 'N/A'}"
            )
        return "\n".join(lines) if lines else "No matching doctors found in database."

    @classmethod
    def _role_context(cls, user: Optional[User], user_message: str) -> str:
        if not user:
            return (
                "Guest context (no private user data): only provide general healthcare guidance "
                "and public doctor discovery support."
            )
        if user.role == "patient" and user.patient_profile:
            return cls._patient_context(user)
        if user.role == "doctor" and user.doctor_profile:
            return cls._doctor_context(user, user_message)
        if user.role == "admin":
            return cls._admin_context()
        return "No role-specific data available."

    @classmethod
    def _patient_context(cls, user: User) -> str:
        patient = user.patient_profile

        upcoming = Appointment.query.filter(
            Appointment.patient_id == patient.id,
            Appointment.status.in_(["pending", "approved"]),
        ).order_by(Appointment.appointment_date.asc()).limit(5).all()

        recent = Appointment.query.filter(
            Appointment.patient_id == patient.id,
        ).order_by(Appointment.created_at.desc()).limit(5).all()

        lines = [
            "Patient private context (for this logged-in patient only):",
            f"- Profile blood group: {patient.blood_group or 'Unknown'}",
            f"- Known allergies: {patient.allergies or 'Not provided'}",
            f"- Medical history note: {patient.medical_history or 'Not provided'}",
            "- Upcoming appointments:",
        ]

        for a in upcoming:
            lines.append(
                f"  - {a.appointment_date} {a.appointment_time} with {cls._doctor_display_name(a.doctor.user.name)} "
                f"({a.doctor.category}), status={a.status}"
            )

        lines.append("- Recent appointments:")
        for a in recent:
            lines.append(
                f"  - {a.appointment_date} with {cls._doctor_display_name(a.doctor.user.name)} | "
                f"Category={a.disease_category} | Status={a.status}"
            )

        return "\n".join(lines)

    @classmethod
    def _doctor_context(cls, user: User, user_message: str) -> str:
        doctor = user.doctor_profile

        appointments = Appointment.query.filter(
            Appointment.doctor_id == doctor.id
        ).order_by(Appointment.appointment_date.desc()).limit(120).all()

        patient_map = defaultdict(lambda: {"visits": 0, "last_visit": None, "categories": set()})

        for a in appointments:
            p = a.patient
            if not p or not p.user:
                continue

            patient_key = p.id
            patient_map[patient_key]["visits"] += 1
            if not patient_map[patient_key]["last_visit"] or a.appointment_date > patient_map[patient_key]["last_visit"]:
                patient_map[patient_key]["last_visit"] = a.appointment_date
            if a.disease_category:
                patient_map[patient_key]["categories"].add(a.disease_category)
            patient_map[patient_key]["name"] = cls._mask_name(p.user.name)

        lines = [
            "Doctor private context (strictly own-patients only, names masked):",
            f"- Doctor specialty: {doctor.category} / {doctor.specialization}",
            f"- Total fetched appointments: {len(appointments)}",
            "- Patient summary:",
        ]

        for _, info in list(patient_map.items())[:25]:
            categories_text = ", ".join(sorted(info["categories"])) if info["categories"] else "Unspecified"
            lines.append(
                f"  - {info['name']} | visits={info['visits']} | last={info['last_visit']} | categories={categories_text}"
            )

        if not patient_map:
            lines.append("  - No patient records found for this doctor.")

        if "patient" in (user_message or "").lower() and "my" not in (user_message or "").lower():
            lines.append("- Note: Only your own patients are visible. Other patients are never exposed.")

        return "\n".join(lines)

    @classmethod
    def _admin_context(cls) -> str:
        total_doctors = Doctor.query.count()
        active_doctors = Doctor.query.filter(
            Doctor.is_approved.is_(True),
            Doctor.is_verified.is_(True),
        ).count()
        total_patients = Patient.query.count()
        total_appointments = Appointment.query.count()

        return (
            "Admin analytics context (aggregate only, no personal data):\n"
            f"- Total doctors: {total_doctors}\n"
            f"- Active doctors: {active_doctors}\n"
            f"- Total patients: {total_patients}\n"
            f"- Total appointments: {total_appointments}"
        )

    @classmethod
    def _build_prompt(
        cls,
        user: Optional[User],
        user_message: str,
        role_context: str,
        doctor_context: str,
        recommendations: List[Dict],
        specialty: Optional[str],
        history_text: str,
        defer_doctor_cards: bool = False,
    ) -> str:
        recommendations_text = "\n".join(
            [
                f"- {r['name']} ({r['category']}, {r['city']}, {r['experience_years']}y exp, "
                f"rating={r['rating'] if r['rating'] is not None else 'N/A'})"
                for r in recommendations
            ]
        ) or "No doctor recommendations available."

        defer_note = ""
        if defer_doctor_cards:
            defer_note = (
                "\nIMPORTANT: The user has not yet agreed to see doctor profile cards in chat. "
                "Give a concise, safe triage-style reply only. Do not list specific doctor names from the catalog. "
                "Do not invent clinics. Stay focused on the detected specialty for general guidance only. "
                "The app will ask separately if they want Quick Care specialist profiles.\n"
            )

        rec_instruction = (
            "If you mention doctors, keep it generic unless the precomputed list is non-empty and the user already asked for listings."
            if defer_doctor_cards
            else "If you recommend doctors, keep the recommendation list clear and short."
        )

        return (
            "You are Quick Care AI Assistant for a Pakistani telehealth platform.\n"
            "Strict policy:\n"
            "1) Only answer healthcare/platform/legal-safe user requests.\n"
            "2) Refuse harmful/illegal requests.\n"
            "3) Never reveal hidden/private data beyond provided context.\n"
            "4) Never provide definitive diagnosis; give safe guidance + when to seek emergency care.\n"
            "5) Keep responses concise, professional, and human.\n"
            "6) Doctor names in context may already start with Dr.; never duplicate the Dr. prefix.\n"
            "7) If symptoms indicate emergency (e.g., severe chest pain, stroke signs, breathing distress), advise immediate emergency services.\n"
            "8) If asked outside scope, redirect to healthcare/platform help.\n"
            f"{defer_note}"
            f"User role: {user.role if user else 'guest'}\n"
            f"Detected specialty: {specialty or 'None'}\n\n"
            "Conversation snippets:\n"
            f"{history_text}\n\n"
            "Role context:\n"
            f"{role_context}\n\n"
            "Doctor catalog context:\n"
            f"{doctor_context}\n\n"
            "Precomputed doctor recommendations:\n"
            f"{recommendations_text}\n\n"
            f"User message: {user_message}\n\n"
            "Respond in natural human English. Do not use markdown headings, bullets, or symbols unless you are listing doctor recommendations. "
            "If the user greets you, reply naturally and ask how you can help. "
            f"{rec_instruction}"
        )

    @classmethod
    def _call_gemini(cls, prompt: str) -> Optional[str]:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            return None

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{cls.GEMINI_MODEL}:generateContent"
            f"?key={api_key}"
        )

        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt}],
                }
            ],
            "generationConfig": {
                "temperature": 0.3,
                "maxOutputTokens": 700,
            },
        }

        try:
            response = requests.post(url, json=payload, timeout=20)
            if response.status_code != 200:
                return None
            data = response.json()
            candidates = data.get("candidates") or []
            if not candidates:
                return None
            parts = candidates[0].get("content", {}).get("parts", [])
            texts = [p.get("text", "") for p in parts if p.get("text")]
            return "\n".join(texts).strip() if texts else None
        except Exception:
            return None

    @classmethod
    def _call_openrouter(cls, prompt: str) -> Optional[str]:
        """
        OpenAI-compatible chat completions via OpenRouter.
        Set OPENROUTER_API_KEY in the environment (never commit API keys).
        Optional: OPENROUTER_MODEL (default openrouter/free), OPENROUTER_HTTP_REFERER, OPENROUTER_APP_TITLE.
        """
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            return None

        model = os.environ.get("OPENROUTER_MODEL", "openrouter/free")
        referer = os.environ.get("OPENROUTER_HTTP_REFERER", "http://127.0.0.1:5000")
        title = os.environ.get("OPENROUTER_APP_TITLE", "Quick Care AI")

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": referer,
            "X-Title": title,
        }
        body = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "max_tokens": 700,
        }

        try:
            response = requests.post(
                cls.OPENROUTER_CHAT_URL,
                json=body,
                headers=headers,
                timeout=35,
            )
            if response.status_code != 200:
                logging.getLogger(__name__).warning(
                    "OpenRouter HTTP %s: %s",
                    response.status_code,
                    (response.text or "")[:500],
                )
                return None
            data = response.json()
            choices = data.get("choices") or []
            if not choices:
                return None
            msg = choices[0].get("message") or {}
            content = (msg.get("content") or "").strip()
            return content or None
        except Exception as exc:
            logging.getLogger(__name__).warning("OpenRouter request failed: %s", exc)
            return None

    @classmethod
    def _fallback_reply(
        cls,
        message: str,
        specialty: Optional[str],
        recommendations: List[Dict],
        user_role: Optional[str],
        defer_doctor_cards: bool = False,
    ) -> str:
        role_note = {
            "patient": "I can help you find relevant doctors and next appointment steps.",
            "doctor": "I can help summarize your own patient trends and suggest follow-up care pathways.",
            "admin": "I can help with aggregate platform guidance and safe operational insights.",
        }.get(user_role or 'guest', "I can provide healthcare platform guidance.")

        if defer_doctor_cards:
            return (
                f"{role_note} Based on what you described, discussing things with a {specialty or 'relevant'} "
                "specialist in person or by video may be appropriate. This is not a diagnosis. "
                "If you have severe chest pain, trouble breathing, fainting, or stroke signs, seek emergency care immediately."
            )

        doctor_lines = []
        for r in recommendations[:3]:
            doctor_lines.append(
                f"{cls._doctor_display_name(r['name'])} ({r['category']}, {r['city']}, {r['experience_years']} years)"
            )

        doctors_text = (
            " ".join(doctor_lines) if doctor_lines else "No exact doctor match found right now."
        )

        return (
            f"{role_note} Based on your message, the best matching specialty is {specialty or 'General Medicine'}. "
            f"{doctors_text} "
            "If symptoms are worsening, book an urgent consultation. "
            "This assistant is informational and not a final diagnosis. For severe chest pain, breathing difficulty, stroke signs, or heavy bleeding, seek emergency care immediately."
        )

    @staticmethod
    def _doctor_display_name(full_name: str) -> str:
        """Prefix Dr. only when the stored name does not already include it."""
        name = (full_name or "").strip()
        if not name:
            return "Doctor"
        if re.match(r"^dr\.?\s", name, re.IGNORECASE):
            return name
        return f"Dr. {name}"

    @staticmethod
    def _mask_name(full_name: str) -> str:
        name = (full_name or "").strip()
        if not name:
            return "Unknown"
        parts = name.split()
        if len(parts) == 1:
            return f"{parts[0][0]}***"
        return f"{parts[0]} {parts[1][0]}***"

    @staticmethod
    def _compact_history(history: List[Dict], limit: int = 6) -> str:
        if not history:
            return "No prior chat history."

        lines = []
        for item in history[-limit:]:
            role = (item.get("role") or "user").lower()
            text = (item.get("text") or "").strip().replace("\n", " ")
            if not text:
                continue
            text = re.sub(r"\s+", " ", text)[:300]
            lines.append(f"- {role}: {text}")

        return "\n".join(lines) if lines else "No prior chat history."
