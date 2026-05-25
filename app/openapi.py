"""
Custom OpenAPI schema generator.

ADK injects internal routes whose Pydantic models use private types
(e.g. MCP / proto-plus) that crash schema generation.
We build the schema ONLY for our custom endpoints so Swagger UI
shows a clean, working documentation page.
"""

from fastapi.openapi.utils import get_openapi

# Paths we own and document automatically via FastAPI
_CUSTOM_PATHS = {
    "/health",
    "/list-apps",
    "/create-session",
    "/chat-history/{user_id}",
    "/chat-history/{user_id}/{session_id}",
    "/set-user-profile/{user_id}",
    "/get-user-profile/{user_id}",
    "/sync-user-profile/{user_id}",
    "/register-caregiver-fcm",
}

# ---------------------------------------------------------------------------
# Report endpoints — documented manually with full response schemas
# because Swagger auto-generation doesn't capture enough detail
# ---------------------------------------------------------------------------

_REPORT_PATHS_MANUAL = {
    "/reports/generate": {
        "post": {
            "tags": ["Health Reports"],
            "summary": "Generate Health Report",
            "description": (
                "Generate an AI health report (daily, weekly, monthly, or emergency). "
                "The report agent aggregates user profile, conversation history, and "
                "medical reports from the database, then produces a markdown report. "
                "The report is stored in the DB and returned.\n\n"
                "to respond depending on model load.\n\n"
                "**For testing without the model:** Use `GET /reports/{user_id}` and "
                "`GET /reports/{user_id}/{report_id}` "
            ),
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "required": ["user_id", "report_type"],
                            "properties": {
                                "user_id": {
                                    "type": "string",
                                    "example": "elder_123",
                                    "description": "The elder's user ID",
                                },
                                "report_type": {
                                    "type": "string",
                                    "enum": ["daily", "weekly", "monthly", "emergency"],
                                    "example": "weekly",
                                    "description": "Type of report to generate",
                                },
                                "start_date": {
                                    "type": "string",
                                    "example": "2026-05-01",
                                    "description": "Override period start (YYYY-MM-DD). Auto-calculated if omitted.",
                                },
                                "end_date": {
                                    "type": "string",
                                    "example": "2026-05-15",
                                    "description": "Override period end (YYYY-MM-DD). Auto-calculated if omitted.",
                                },
                                "notify_caregiver": {
                                    "type": "boolean",
                                    "default": False,
                                    "description": "If true, sends FCM push notification to all registered caregivers after report is generated.",
                                },
                            },
                        },
                        "examples": {
                            "Weekly Report": {
                                "summary": "Generate a weekly report",
                                "value": {
                                    "user_id": "elder_123",
                                    "report_type": "weekly",
                                },
                            },
                            "Emergency + Notify": {
                                "summary": "SOS emergency with caregiver notification",
                                "value": {
                                    "user_id": "elder_123",
                                    "report_type": "emergency",
                                    "notify_caregiver": True,
                                },
                            },
                            "Custom Date Range": {
                                "summary": "Report for a specific date range",
                                "value": {
                                    "user_id": "elder_123",
                                    "report_type": "monthly",
                                    "start_date": "2026-04-01",
                                    "end_date": "2026-04-30",
                                },
                            },
                        },
                    }
                },
            },
            "responses": {
                "200": {
                    "description": "Report generated successfully",
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "success": {"type": "boolean", "example": True},
                                    "report_id": {"type": "string", "example": "HR_a1b2c3d4e5f6"},
                                    "user_id": {"type": "string", "example": "elder_123"},
                                    "report_type": {"type": "string", "example": "weekly"},
                                    "period": {
                                        "type": "object",
                                        "properties": {
                                            "start": {"type": "string", "example": "2026-05-17"},
                                            "end": {"type": "string", "example": "2026-05-24"},
                                        },
                                    },
                                    "title": {"type": "string", "example": "تقرير أسبوعي — أحمد"},
                                    "overall_status": {
                                        "type": "string",
                                        "enum": ["good", "moderate", "concerning", "critical"],
                                        "example": "good",
                                    },
                                    "content": {
                                        "type": "string",
                                        "description": "Full markdown report text. Render as markdown in Flutter (same as chat messages).",
                                        "example": "📊 تقرير أسبوعي — أحمد\n\nيا فندم، ده ملخص الأسبوع 💚\n\n📊 نظرة عامة:\nالحمد لله، الأسبوع ده كان كويس...\n\n🍽️ التغذية:\n• الوجبات كانت متوازنة...\n\n📌 التوصيات:\n1. حافظ على المشي يومياً\n2. اشرب مية كفاية\n\nربنا يديم عليك الصحة 💚",
                                    },
                                    "generated_at": {"type": "string", "example": "2026-05-24T23:00:00.123456"},
                                    "stored_in_db": {"type": "boolean", "example": True},
                                    "notification": {
                                        "type": "object",
                                        "nullable": True,
                                        "description": "FCM notification result (null if notify_caregiver was false)",
                                        "properties": {
                                            "sent": {"type": "integer", "example": 1},
                                            "failed": {"type": "integer", "example": 0},
                                            "details": {
                                                "type": "array",
                                                "items": {
                                                    "type": "object",
                                                    "properties": {
                                                        "caregiver": {"type": "string", "example": "محمد"},
                                                        "status": {"type": "string", "example": "sent"},
                                                    },
                                                },
                                            },
                                        },
                                    },
                                },
                            },
                        }
                    },
                },
                "400": {
                    "description": "Invalid report_type",
                    "content": {
                        "application/json": {
                            "example": {"detail": "Invalid report_type. Must be one of: daily, weekly, monthly, emergency"}
                        }
                    },
                },
                "500": {
                    "description": "Report generation failed (model error or timeout)",
                    "content": {
                        "application/json": {
                            "example": {"detail": "Report generation failed: Connection refused"}
                        }
                    },
                },
            },
        }
    },
    "/reports/{user_id}": {
        "get": {
            "tags": ["Health Reports"],
            "summary": "List Reports",
            "description": (
                "List all health reports for a user. Reads from the database — "
                "does NOT invoke the AI model. Fast response.\n\n"
                "Use `report_type` query param to filter by type."
            ),
            "parameters": [
                {"name": "user_id", "in": "path", "required": True, "schema": {"type": "string", "example": "elder_123"}},
                {"name": "report_type", "in": "query", "required": False, "schema": {"type": "string", "enum": ["daily", "weekly", "monthly", "emergency"]}},
                {"name": "limit", "in": "query", "required": False, "schema": {"type": "integer", "default": 20}},
            ],
            "responses": {
                "200": {
                    "description": "List of report summaries (no full content — use detail endpoint for full content)",
                    "content": {
                        "application/json": {
                            "example": {
                                "success": True,
                                "user_id": "elder_123",
                                "count": 3,
                                "reports": [
                                    {
                                        "report_id": "HR_a1b2c3d4e5f6",
                                        "user_id": "elder_123",
                                        "report_type": "weekly",
                                        "period_start": "2026-05-17",
                                        "period_end": "2026-05-24",
                                        "title": "تقرير أسبوعي — أحمد",
                                        "overall_status": "good",
                                        "generated_at": "2026-05-24T23:00:00",
                                    },
                                    {
                                        "report_id": "HR_b2c3d4e5f6a7",
                                        "user_id": "elder_123",
                                        "report_type": "daily",
                                        "period_start": "2026-05-24",
                                        "period_end": "2026-05-24",
                                        "title": "تقرير يومي — أحمد",
                                        "overall_status": "moderate",
                                        "generated_at": "2026-05-24T23:00:00",
                                    },
                                ],
                            }
                        }
                    },
                }
            },
        }
    },
    "/reports/{user_id}/{report_id}": {
        "get": {
            "tags": ["Health Reports"],
            "summary": "Get Report Detail",
            "description": (
                "Get the full content of a specific health report. "
                "Reads from the database — does NOT invoke the AI model. Fast response.\n\n"
                "The `content` field contains the full markdown report. "
                "Render it in Flutter the same way you render chat messages."
            ),
            "parameters": [
                {"name": "user_id", "in": "path", "required": True, "schema": {"type": "string", "example": "elder_123"}},
                {"name": "report_id", "in": "path", "required": True, "schema": {"type": "string", "example": "HR_a1b2c3d4e5f6"}},
            ],
            "responses": {
                "200": {
                    "description": "Full report with markdown content",
                    "content": {
                        "application/json": {
                            "example": {
                                "success": True,
                                "report": {
                                    "report_id": "HR_a1b2c3d4e5f6",
                                    "user_id": "elder_123",
                                    "report_type": "weekly",
                                    "period_start": "2026-05-17",
                                    "period_end": "2026-05-24",
                                    "title": "تقرير أسبوعي — أحمد",
                                    "content": "📊 تقرير أسبوعي — أحمد\n\nيا فندم، ده ملخص الأسبوع 💚\n\n📊 نظرة عامة:\nالحمد لله، الأسبوع ده كان كويس...\n\n🍽️ التغذية:\n• الوجبات كانت متوازنة...\n\n💪 النشاط البدني:\n• مشي خفيف 3 مرات...\n\n💊 الأدوية:\n• Metformin 500mg — منتظم\n\n📌 التوصيات:\n1. حافظ على المشي يومياً\n2. اشرب مية كفاية\n3. خلي بالك من مواعيد الأدوية\n\nربنا يديم عليك الصحة يا فندم 💚",
                                    "overall_status": "good",
                                    "key_highlights": "[]",
                                    "recommendations": "[]",
                                    "doctor_notes": "",
                                    "generated_at": "2026-05-24T23:00:00",
                                },
                            }
                        }
                    },
                },
                "404": {
                    "description": "Report not found",
                    "content": {"application/json": {"example": {"detail": "Report not found"}}},
                },
                "403": {
                    "description": "Access denied (user_id doesn't match report owner)",
                    "content": {"application/json": {"example": {"detail": "Access denied"}}},
                },
            },
        }
    },
    "/reports/medical/{user_id}": {
        "get": {
            "tags": ["Health Reports"],
            "summary": "Get Medical Image Reports",
            "description": (
                "List all analyzed medical reports from image analysis for a user. "
                "Reads from database — does NOT invoke the AI model."
            ),
            "parameters": [
                {"name": "user_id", "in": "path", "required": True, "schema": {"type": "string", "example": "elder_123"}},
            ],
            "responses": {
                "200": {
                    "description": "List of analyzed medical report records",
                    "content": {
                        "application/json": {
                            "example": {
                                "success": True,
                                "user_id": "elder_123",
                                "count": 1,
                                "reports": [
                                    {
                                        "report_id": "MR_abc123",
                                        "user_id": "elder_123",
                                        "report_type": "blood_test",
                                        "report_date": "2026-05-20",
                                        "key_findings": "Glucose: 150 mg/dL (elevated), HbA1c: 7.2%",
                                        "lab_values": "[{\"name\": \"Glucose\", \"value\": \"150\", \"unit\": \"mg/dL\", \"status\": \"high\"}]",
                                        "health_summary": "Elevated blood sugar levels consistent with diabetes management",
                                        "severity_level": "moderate",
                                        "recommendations": "Continue Metformin, monitor fasting glucose",
                                        "scanned_at": "2026-05-20T14:30:00",
                                    }
                                ],
                            }
                        }
                    },
                }
            },
        }
    },
    "/reports/seed": {
        "post": {
            "tags": ["Health Reports"],
            "summary": "Seed Test Data",
            "description": (
                "Inject sample health reports and medical reports into the database for testing. "
                "Call this ONCE to populate test data, then use the list/detail endpoints.\n\n"
                "**Does NOT invoke the AI model.** Fast response.\n\n"
                "After seeding, test with:\n"
                "- `GET /reports/{user_id}` — list all seeded reports\n"
                "- `GET /reports/{user_id}/HR_seed_daily_001` — daily report detail\n"
                "- `GET /reports/{user_id}/HR_seed_weekly_001` — weekly report detail\n"
                "- `GET /reports/{user_id}/HR_seed_monthly_001` — monthly report detail\n"
                "- `GET /reports/{user_id}/HR_seed_emergency_001` — emergency report detail\n"
                "- `GET /reports/medical/{user_id}` — medical image reports"
            ),
            "parameters": [
                {"name": "user_id", "in": "query", "required": False, "schema": {"type": "string", "default": "elder_123"}},
                {"name": "clear", "in": "query", "required": False, "schema": {"type": "boolean", "default": False}},
            ],
            "responses": {
                "200": {
                    "description": "Seed data inserted",
                    "content": {
                        "application/json": {
                            "example": {
                                "success": True,
                                "user_id": "elder_123",
                                "cleared_existing": False,
                                "health_reports_inserted": 4,
                                "medical_reports_inserted": 2,
                                "test_endpoints": {
                                    "list_reports": "/reports/elder_123",
                                    "daily_detail": "/reports/elder_123/HR_seed_daily_001",
                                    "weekly_detail": "/reports/elder_123/HR_seed_weekly_001",
                                    "monthly_detail": "/reports/elder_123/HR_seed_monthly_001",
                                    "emergency_detail": "/reports/elder_123/HR_seed_emergency_001",
                                    "medical_reports": "/reports/medical/elder_123",
                                },
                            }
                        }
                    },
                }
            },
        }
    },
}


# ADK paths we document manually (their models crash schema generation)
_ADK_PATHS_MANUAL = {
    "/run_sse": {
        "post": {
            "tags": ["Agent"],
            "summary": "Run Agent",
            "description": (
                "Send a message to the SenioCare agent and receive a response. "
                "Use streaming: false for a single JSON response, "
                "or streaming: true for Server-Sent Events."
            ),
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "required": ["app_name", "user_id", "session_id", "new_message"],
                            "properties": {
                                "app_name":    {"type": "string", "example": "seniocare"},
                                "user_id":     {"type": "string", "example": "user_123"},
                                "session_id":  {"type": "string", "example": "session_abc"},
                                "new_message": {
                                    "type": "object",
                                    "properties": {
                                        "role": {"type": "string", "enum": ["user"]},
                                        "parts": {
                                            "type": "array",
                                            "items": {
                                                "type": "object",
                                                "properties": {
                                                    "text": {"type": "string", "example": "مرحبا"}
                                                }
                                            }
                                        }
                                    }
                                },
                                "streaming": {"type": "boolean", "example": False},
                            }
                        }
                    }
                }
            },
            "responses": {
                "200": {
                    "description": "Agent response with events",
                    "content": {
                        "application/json": {
                            "example": {"events": [{"type": "agent_response", "content": "..."}]}
                        }
                    }
                }
            }
        }
    },
    "/apps/{app_name}/users/{user_id}/sessions/{session_id}": {
        "post": {
            "tags": ["Sessions"],
            "summary": "Create Session (ADK)",
            "description": "Create a new conversation session via ADK. Prefer POST /create-session (auto-generates session ID).",
            "parameters": [
                {"name": "app_name",    "in": "path", "required": True, "schema": {"type": "string", "example": "seniocare"}},
                {"name": "user_id",     "in": "path", "required": True, "schema": {"type": "string", "example": "user_123"}},
                {"name": "session_id",  "in": "path", "required": True, "schema": {"type": "string", "example": "session_abc"}},
            ],
            "requestBody": {"content": {"application/json": {"example": {}}}},
            "responses": {"200": {"description": "Session created successfully"}}
        },
        "get": {
            "tags": ["Sessions"],
            "summary": "Get Session",
            "description": "Retrieve session info and state.",
            "parameters": [
                {"name": "app_name",   "in": "path", "required": True, "schema": {"type": "string", "example": "seniocare"}},
                {"name": "user_id",    "in": "path", "required": True, "schema": {"type": "string", "example": "user_123"}},
                {"name": "session_id", "in": "path", "required": True, "schema": {"type": "string", "example": "session_abc"}},
            ],
            "responses": {"200": {"description": "Session data"}}
        },
        "delete": {
            "tags": ["Sessions"],
            "summary": "Delete Session",
            "description": "Delete a specific session.",
            "parameters": [
                {"name": "app_name",   "in": "path", "required": True, "schema": {"type": "string", "example": "seniocare"}},
                {"name": "user_id",    "in": "path", "required": True, "schema": {"type": "string", "example": "user_123"}},
                {"name": "session_id", "in": "path", "required": True, "schema": {"type": "string", "example": "session_abc"}},
            ],
            "responses": {"200": {"description": "Session deleted"}}
        },
    },
    "/apps/{app_name}/users/{user_id}/sessions": {
        "get": {
            "tags": ["Sessions"],
            "summary": "List Sessions",
            "description": "List all sessions for a user.",
            "parameters": [
                {"name": "app_name", "in": "path", "required": True, "schema": {"type": "string", "example": "seniocare"}},
                {"name": "user_id",  "in": "path", "required": True, "schema": {"type": "string", "example": "user_123"}},
            ],
            "responses": {"200": {"description": "List of session IDs"}}
        }
    },
}

_TAG_ORDER = [
    {"name": "Health",          "description": "Service health and discovery"},
    {"name": "Sessions",        "description": "Conversation session management"},
    {"name": "Chat History",    "description": "Conversation history with headlines"},
    {"name": "User Profile",    "description": "Push/pull user health profile data"},
    {"name": "Health Reports",  "description": "AI-generated health reports and medical report history"},
    {"name": "Agent",           "description": "Send messages to the SenioCare AI agent"},
]


def make_custom_openapi(app):
    """Return a custom_openapi() closure bound to the given FastAPI app."""

    def custom_openapi():
        # Only auto-generate for simple endpoints (not reports — we do those manually)
        safe_routes = [
            r for r in app.routes
            if hasattr(r, "path") and r.path in _CUSTOM_PATHS
        ]

        try:
            schema = get_openapi(
                title="SenioCare AI Agent API",
                version="3.1.0",
                description="AI-powered healthcare assistant API for elderly care.",
                routes=safe_routes,
            )
        except Exception:
            schema = {
                "openapi": "3.1.0",
                "info": {"title": "SenioCare AI Agent API", "version": "3.1.0"},
                "paths": {},
            }

        # Add manually documented paths
        for path, methods in _ADK_PATHS_MANUAL.items():
            schema["paths"][path] = methods

        for path, methods in _REPORT_PATHS_MANUAL.items():
            schema["paths"][path] = methods

        schema["tags"] = _TAG_ORDER
        return schema

    return custom_openapi
