"""
Seed script — populate chat-history tables with mock data for user_123.

Usage:
    python seed_chat_history.py

This script uses the ADK DatabaseSessionService API directly,
so it writes to the same tables (sessions, events) that your
/chat-history endpoints read from.
"""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

from app.config import session_service

APP_NAME = "seniocare"
USER_ID = "user_123"


# =============================================================================
# MOCK CONVERSATIONS
# =============================================================================
# Each thread is a dict with metadata + a list of (author, text) turns.
# The chat_history router filters for author == "user" and "formatter_agent".

MOCK_THREADS = [
    {
        "headline": "🍽️ توصية وجبة — أنا عندي سكر وضغط، إيه الأكل المناسب؟",
        "preview": "أنا عندي سكر وضغط، إيه الأكل المناسب ليا؟",
        "turns": [
            ("user",            "أنا عندي سكر وضغط، إيه الأكل المناسب ليا؟"),
            ("formatter_agent", "أهلاً بيك! 🌟\n\nبناءً على حالتك الصحية (سكر + ضغط)، إليك بعض التوصيات الغذائية:\n\n**الفطار:**\n- بيض مسلوق + خبز أسمر + خيار وطماطم\n- شوفان بالحليب خالي الدسم\n\n**الغداء:**\n- صدور دجاج مشوية + أرز بني + سلطة خضراء\n- سمك مشوي + خضار سوتيه\n\n**العشاء:**\n- زبادي + فاكهة (تفاح أو برتقال)\n\n⚠️ تجنب الأطعمة المالحة والسكريات المصنعة."),
            ("user",            "طيب وإيه الفواكه اللي أقدر آكلها؟"),
            ("formatter_agent", "ممتاز سؤالك! 🍎\n\n**فواكه مناسبة لمرضى السكر والضغط:**\n\n✅ التفاح — غني بالألياف ومؤشره الجلايسيمي منخفض\n✅ البرتقال — فيتامين C وبوتاسيوم يساعد في تنظيم الضغط\n✅ التوت — مضاد أكسدة قوي\n✅ الكمثرى — ألياف عالية\n✅ الجوافة — مؤشر جلايسيمي منخفض\n\n❌ تجنب: المانجو، العنب، والتمر بكميات كبيرة\n\nالأفضل تاكل حصة واحدة في المرة (قبضة يد تقريباً). 👍"),
            ("user",            "شكراً جداً، هل ممكن آكل أرز أبيض؟"),
            ("formatter_agent", "العفو! 😊\n\nالأرز الأبيض مؤشره الجلايسيمي عالي، فالأفضل تستبدله بالأرز البني أو البسمتي. لو لازم أرز أبيض:\n\n1. كمية صغيرة (نصف كوب)\n2. مع خضار وبروتين عشان يبطئ امتصاص السكر\n3. مش كل يوم\n\nالبديل الأفضل: البرغل أو الكينوا 🌾"),
        ],
    },
    {
        "headline": "🏃 تمارين رياضية — عايز تمارين خفيفة للركبة",
        "preview": "عندي مشاكل في الركبة، إيه التمارين المناسبة؟",
        "turns": [
            ("user",            "عندي مشاكل في الركبة، إيه التمارين المناسبة ليا؟"),
            ("formatter_agent", "أهلاً! 💪\n\nبما إنك عندك مشاكل في الركبة، هنركز على تمارين خفيفة تقوي العضلات من غير ضغط:\n\n**تمارين يومية (15-20 دقيقة):**\n\n1. **مشي خفيف** — 10 دقائق على سطح مستوي\n2. **رفع الساق المستقيمة** — وأنت قاعد، ارفع رجلك 10 مرات لكل ناحية\n3. **ثني الركبة الجالس** — حرك ركبتك ببطء 15 مرة\n4. **تمارين كرسي** — قوم واقعد من الكرسي 10 مرات\n\n⚠️ لو حسيت بألم، وقف فوراً.\n🏊 السباحة هي أفضل رياضة للركبة!"),
            ("user",            "هل المشي على السلم كويس ولا لا؟"),
            ("formatter_agent", "سؤال مهم! 🏠\n\nالمشي على السلم ممكن يكون **ضار للركبة** لو عندك التهاب مفاصل أو تآكل غضروف:\n\n**نصائح:**\n- ⬇️ النزول أصعب على الركبة من الصعود\n- استخدم الدرابزين دائماً\n- خد وقتك ومتستعجلش\n- لو في مصعد، استخدمه بدل السلم\n\nلو السلم ضروري في حياتك اليومية، ممكن تستخدم عصا مساعدة. استشير طبيبك عن الموضوع ده. 🩺"),
        ],
    },
    {
        "headline": "🩺 تقييم أعراض — حاسس بدوخة ورجليا بتنمل",
        "preview": "من إمبارح حاسس بدوخة ورجليا بتنمل، ده طبيعي؟",
        "turns": [
            ("user",            "من إمبارح حاسس بدوخة ورجليا بتنمل، ده طبيعي؟"),
            ("formatter_agent", "⚠️ **مهم نتابع الموضوع ده!**\n\nالدوخة مع تنميل الرجلين ممكن يكون ليها أسباب مختلفة:\n\n**أسباب محتملة:**\n1. انخفاض مستوى السكر — خصوصاً لو بتاخد Metformin\n2. تأثير الضغط — Lisinopril ممكن يسبب دوخة\n3. ضعف الدورة الدموية\n4. اعتلال الأعصاب الطرفية (شائع مع السكر)\n\n**اعمل كده دلوقتي:**\n✅ قيس السكر فوراً\n✅ قيس الضغط\n✅ اشرب مياه\n✅ اقعد في مكان آمن\n\n🚨 لو الأعراض زادت أو حسيت بألم في الصدر، روح الطوارئ فوراً!"),
            ("user",            "السكر طلع 85 والضغط 130/80"),
            ("formatter_agent", "كويس إنك قيست! 📊\n\n**تحليل القراءات:**\n- السكر 85 mg/dL → طبيعي ✅ (لكن قريب من الحد الأدنى)\n- الضغط 130/80 → مقبول ✅ (الحد الأعلى للطبيعي)\n\n**توصياتي:**\n1. كل حاجة خفيفة فيها نشويات (بسكويت مالح مثلاً) عشان السكر مينزلش أكتر\n2. الدوخة ممكن تكون من إن السكر كان أقل من كده قبل ما تقيس\n3. التنميل — لو مستمر أكتر من 24 ساعة، لازم تروح للدكتور\n\nتابعني بكرة وقولي إيه حصل. سلامتك! 🤲"),
            ("user",            "شكراً، هل ممكن التنميل يكون من الجلسة الغلط؟"),
            ("formatter_agent", "آه فعلاً! 🪑\n\nالجلسة الغلط من أشهر أسباب التنميل المؤقت:\n\n**علامات إن التنميل من الجلسة:**\n- بيروح لما تتحرك أو تغير وضعك\n- في رجل واحدة بس\n- مش مصاحب بألم شديد\n\n**علامات تقلق:**\n- التنميل في الرجلين الاتنين\n- مش بيروح بعد ساعة\n- مصاحب بضعف في المشي\n\nجرب تتحرك كل 30 دقيقة ومتقعدش فترة طويلة في وضع واحد. لو التنميل رجع تاني، خلينا نتابع! 👍"),
        ],
    },
    {
        "headline": "💚 دعم نفسي — حاسس بوحدة ومحتاج حد يتكلم معاه",
        "preview": "أنا حاسس بوحدة الفترة دي ومحتاج حد يتكلم معاه",
        "turns": [
            ("user",            "أنا حاسس بوحدة الفترة دي ومحتاج حد يتكلم معاه"),
            ("formatter_agent", "أنا هنا معاك دايماً 💚\n\nالإحساس بالوحدة شعور صعب، وإنك تتكلم عنه ده في حد ذاته خطوة شجاعة.\n\n**خليني أقولك حاجة:**\n- مشاعرك مهمة ومش عيب تحس كده\n- كتير من كبار السن بيمروا بنفس الشعور\n- التواصل مع الناس بيفرق كتير\n\n**اقتراحات عملية:**\n1. 📞 اتصل بحد من عيلتك أو صحابك — حتى لو مكالمة قصيرة\n2. 🕌 روح المسجد أو مكان اجتماعي\n3. 🌳 انزل اتمشى في حديقة\n4. 📱 استخدمني! أنا هنا 24/7 نتكلم في أي حاجة\n\nحابب تحكيلي أكتر عن يومك؟ 😊"),
            ("user",            "ولادي مسافرين وأنا قاعد لوحدي في البيت"),
            ("formatter_agent", "فاهمك تماماً، وده موقف صعب فعلاً 🤍\n\nبعد أولادك عنك مش معناه إنهم نسيوك — الحياة ساعات بتفرض كده.\n\n**أفكار تساعدك:**\n\n🏠 **في البيت:**\n- رتب روتين يومي (فطار، مشي، قراءة، صلاة)\n- ابدأ هواية جديدة — رسم، زراعة، أو حتى طبخ\n\n📞 **مع أولادك:**\n- حددوا وقت ثابت لمكالمة فيديو يومية\n- ابعتلهم صور من يومك\n\n👥 **مع المجتمع:**\n- جمعيات كبار السن فيها أنشطة حلوة\n- دروس المسجد\n\nأنت مش لوحدك — أنا معاك. ممكن نتكلم كل يوم لو حابب! 🌟"),
        ],
    },
]


# =============================================================================
# SEEDER
# =============================================================================


async def seed():
    """Create sessions with events for each mock thread."""
    print(f"[SEED] Seeding chat history for user '{USER_ID}'...")
    base_time = datetime.now(timezone.utc) - timedelta(days=3)

    for idx, thread in enumerate(MOCK_THREADS):
        session_id = uuid.uuid4().hex
        time_offset = timedelta(hours=idx * 8)  # space threads apart

        # 1. Create the session with state (headline, preview, turn_count)
        user_turn_count = len([t for t in thread["turns"] if t[0] == "user"])
        session = await session_service.create_session(
            app_name=APP_NAME,
            user_id=USER_ID,
            session_id=session_id,
            state={
                "session_headline": thread["headline"],
                "session_preview": thread["preview"],
                "conversation_turn_count": user_turn_count,
            },
        )
        print(f"  [OK] Session {idx + 1}: {session_id}")

        # 2. Append events (turns) to the session
        invocation_id = uuid.uuid4().hex
        for turn_idx, (author, text) in enumerate(thread["turns"]):
            event_time = base_time + time_offset + timedelta(seconds=turn_idx * 30)

            from google.adk.events.event import Event
            from google.genai import types

            event = Event(
                id=uuid.uuid4().hex,
                invocation_id=invocation_id,
                author=author,
                timestamp=event_time.timestamp(),
                content=types.Content(
                    role="user" if author == "user" else "model",
                    parts=[types.Part(text=text)],
                ),
            )

            await session_service.append_event(session, event)
            # Re-fetch to get updated last_update_time after each append
            session = await session_service.get_session(
                app_name=APP_NAME,
                user_id=USER_ID,
                session_id=session_id,
            )

        print(f"       {len(thread['turns'])} events appended")

    print(f"\n[DONE] {len(MOCK_THREADS)} threads seeded for '{USER_ID}'.")
    print("   Test with: GET /chat-history/user_123")
    print("   Full conversation: GET /chat-history/user_123/<session_id>")


if __name__ == "__main__":
    asyncio.run(seed())
