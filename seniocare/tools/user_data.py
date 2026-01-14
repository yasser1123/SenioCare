"""User data tool - retrieves user profile information."""

def get_user_profile(user_id: str) -> dict:
    """
    Retrieves the user profile including conditions, medications, and allergies.
    
    Args:
        user_id: The unique identifier for the user.
        
    Returns:
        dict: User profile with conditions, medications, allergies, and preferences.
    """
    # Mock user database
    users = {
        "user_001": {
            "user_id": "user_001",
            "name": "Ahmed",
            "age": 72,
            "language": "ar-EG",
            "conditions": ["diabetes", "hypertension"],
            "allergies": ["penicillin", "shellfish"],
            "medications": [
                {"name": "Metformin", "dose": "500mg", "schedule": ["08:00", "20:00"]},
                {"name": "Lisinopril", "dose": "10mg", "schedule": ["09:00"]}
            ],
            "mobility": "limited",
            "dietary_preferences": ["halal", "low_sodium"],
            "caregiver_id": "caregiver_001",
            "emergency_contact": "+20123456789"
        },
        "user_002": {
            "user_id": "user_002",
            "name": "Fatma",
            "age": 68,
            "language": "ar-EG",
            "conditions": ["arthritis", "osteoporosis"],
            "allergies": ["nuts"],
            "medications": [
                {"name": "Calcium", "dose": "600mg", "schedule": ["08:00"]},
                {"name": "Vitamin D", "dose": "1000IU", "schedule": ["08:00"]}
            ],
            "mobility": "moderate",
            "dietary_preferences": ["halal"],
            "caregiver_id": "caregiver_002",
            "emergency_contact": "+20198765432"
        }
    }
    
    if user_id in users:
        return {"status": "success", "profile": users[user_id]}
    else:
        return {
            "status": "error",
            "error_message": f"User '{user_id}' not found. Please provide user information."
        }
