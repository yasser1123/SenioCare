"""
SQLite Test Database for SenioCare Tools.

Creates and manages a test database with sample data derived from
the real dataset schemas (DDID, USDA, Various Datasets).
This is for testing AI agent tool-calling behavior.

Tables:
    - meals: Food items with nutritional info
    - condition_dietary_rules: Nutrient thresholds per health condition
    - drug_food_interactions: Drug-food interaction records
    - disease_symptoms: Disease-to-symptom mappings with severity
    - disease_precautions: Precautionary measures per disease
    - food_allergens: Food-to-allergen category mappings
    - medications: User medication schedules
    - exercises: Exercise recommendations by mobility level
    - medical_reports: Analyzed medical report results (from image analysis)
"""

import sqlite3
import json
import os

# Database file path
DB_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(DB_DIR, "seniocare_test.db")


def get_connection() -> sqlite3.Connection:
    """Get a connection to the test database. Creates it if it doesn't exist."""
    if not os.path.exists(DB_PATH):
        _initialize_database()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Return rows as dict-like objects
    return conn


def _initialize_database():
    """Create all tables and populate with sample test data."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Enable WAL mode for better concurrent reads
    cursor.execute("PRAGMA journal_mode=WAL")

    _create_tables(cursor)
    _insert_sample_meals(cursor)
    _insert_condition_rules(cursor)
    _insert_drug_food_interactions(cursor)
    _insert_disease_symptoms(cursor)
    _insert_disease_precautions(cursor)
    _insert_food_allergens(cursor)
    _insert_medications(cursor)
    _insert_exercises(cursor)

    conn.commit()
    conn.close()


def _create_tables(cursor: sqlite3.Cursor):
    """Create all database tables."""

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS meals (
            meal_id        TEXT PRIMARY KEY,
            name_ar        TEXT NOT NULL,
            name_en        TEXT NOT NULL,
            meal_type      TEXT NOT NULL,
            category       TEXT,
            ingredients    TEXT NOT NULL,
            energy_kcal    REAL,
            protein_g      REAL,
            fat_g          REAL,
            carbohydrate_g REAL,
            fiber_g        REAL,
            sodium_mg      REAL,
            sugar_g        REAL,
            prep_time      TEXT,
            notes_ar       TEXT,
            notes_en       TEXT,
            recipe_steps   TEXT,
            recipe_tips    TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS condition_dietary_rules (
            rule_id     TEXT PRIMARY KEY,
            condition   TEXT NOT NULL UNIQUE,
            avoid_high  TEXT,
            prefer_high TEXT,
            avoid_foods TEXT,
            max_values  TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS drug_food_interactions (
            interaction_id TEXT PRIMARY KEY,
            drug_name      TEXT NOT NULL,
            food_name      TEXT NOT NULL,
            effect         TEXT NOT NULL,
            severity       TEXT,
            conclusion     TEXT,
            advice         TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS disease_symptoms (
            disease_id   TEXT PRIMARY KEY,
            disease_name TEXT NOT NULL,
            symptoms     TEXT NOT NULL,
            severity     TEXT NOT NULL,
            description  TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS disease_precautions (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            disease_id TEXT NOT NULL,
            precaution TEXT NOT NULL,
            FOREIGN KEY (disease_id) REFERENCES disease_symptoms(disease_id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS food_allergens (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            food_name TEXT NOT NULL,
            allergen  TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS medications (
            med_id       TEXT PRIMARY KEY,
            user_id      TEXT NOT NULL,
            name         TEXT NOT NULL,
            dose         TEXT NOT NULL,
            schedule     TEXT NOT NULL,
            purpose_ar   TEXT,
            purpose_en   TEXT,
            instructions_ar TEXT,
            instructions_en TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS exercises (
            exercise_id   TEXT PRIMARY KEY,
            name_ar       TEXT NOT NULL,
            name_en       TEXT NOT NULL,
            mobility_level TEXT NOT NULL,
            exercise_type  TEXT NOT NULL,
            duration       TEXT,
            steps          TEXT NOT NULL,
            benefits_ar    TEXT,
            benefits_en    TEXT,
            safety_ar      TEXT,
            safety_en      TEXT,
            avoid_conditions TEXT
        )
    """)

    # Medical reports table (for image analysis results)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS medical_reports (
            report_id      TEXT PRIMARY KEY,
            user_id        TEXT NOT NULL,
            report_type    TEXT NOT NULL,
            report_date    TEXT,
            key_findings   TEXT NOT NULL,
            lab_values     TEXT NOT NULL,
            health_summary TEXT,
            severity_level TEXT,
            recommendations TEXT NOT NULL,
            scanned_at     TEXT NOT NULL,
            raw_response   TEXT
        )
    """)

    # Create indexes for common query patterns
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_meals_type ON meals(meal_type)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_drug_interactions_drug ON drug_food_interactions(drug_name)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_drug_interactions_food ON drug_food_interactions(food_name)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_allergens_allergen ON food_allergens(allergen)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_medications_user ON medications(user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_exercises_mobility ON exercises(mobility_level)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_precautions_disease ON disease_precautions(disease_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_medical_reports_user ON medical_reports(user_id)")


def _insert_sample_meals(cursor: sqlite3.Cursor):
    """Insert sample meal data (Egyptian + general healthy meals) with full recipes."""
    meals = [
        # === BREAKFAST ===
        ("M001", "فول مدمس بزيت الزيتون", "Foul Medames with Olive Oil", "breakfast", "legumes",
         json.dumps(["foul", "olive oil", "lemon", "cumin"]),
         280, 15.0, 8.0, 35.0, 9.0, 50.0, 2.0, "15 min",
         "منخفض السكر، غني بالألياف", "Low sugar, high fiber",
         json.dumps(["انقع الفول ليلة كاملة في مية", "اسلقه في حلة الضغط ساعة", "صفيه وحطه في طبق", "ضيف زيت الزيتون والليمون والكمون", "قدمه دافي مع عيش أسمر"]),
         "ممكن تضيف طحينة أو بيض مسلوق حسب رغبتك"),

        ("M002", "بيض مسلوق مع خبز أسمر", "Boiled Eggs with Whole Wheat Bread", "breakfast", "protein",
         json.dumps(["eggs", "whole wheat bread", "cucumber", "tomato"]),
         310, 18.0, 12.0, 30.0, 4.0, 180.0, 3.0, "10 min",
         "بروتين عالي، كربوهيدرات معتدلة", "High protein, moderate carbs",
         json.dumps(["اسلق البيض في مية 10 دقايق", "قشر البيض وقطعه أنصاص", "قطع الخيار والطماطم شرائح", "قدم البيض مع العيش الأسمر والخضار"]),
         "البيض المسلوق نص سوا أسهل في الهضم"),

        ("M003", "شوفان بالحليب والفواكه", "Oatmeal with Milk and Fruits", "breakfast", "grains",
         json.dumps(["oats", "milk", "banana", "honey", "cinnamon"]),
         350, 12.0, 7.0, 55.0, 6.0, 70.0, 18.0, "10 min",
         "طاقة مستدامة", "Sustained energy",
         json.dumps(["سخن الحليب على نار هادية", "ضيف الشوفان وقلب كويس", "سيبه 5 دقايق على نار واطية", "ضيف الموز المقطع والعسل والقرفة"]),
         "ممكن تستخدم حليب قليل الدسم لسعرات أقل"),

        ("M004", "جبنة قريش مع خضار", "Cottage Cheese with Vegetables", "breakfast", "dairy",
         json.dumps(["cottage cheese", "cucumber", "tomato", "bell pepper", "olive oil"]),
         200, 14.0, 9.0, 12.0, 2.0, 320.0, 4.0, "5 min",
         "غني بالكالسيوم", "Rich in calcium",
         json.dumps(["قطع الخيار والطماطم والفلفل مكعبات صغيرة", "حط الجبنة القريش في طبق", "ضيف الخضار المقطعة فوقيها", "رش زيت الزيتون وقدمها"]),
         "الجبنة القريش غنية بالكالسيوم ومنخفضة الدهون"),

        # === LUNCH ===
        ("M005", "سمك مشوي مع خضار", "Grilled Fish with Vegetables", "lunch", "protein",
         json.dumps(["fish", "broccoli", "carrot", "lemon", "olive oil"]),
         320, 35.0, 10.0, 15.0, 5.0, 90.0, 3.0, "30 min",
         "منخفض الدهون، غني بالأوميجا 3", "Low fat, rich in omega-3",
         json.dumps(["تبل السمك بالليمون والملح والفلفل", "سخن الشواية على نار متوسطة", "اشوي السمك 7 دقايق كل جانب", "اسلق البروكلي والجزر على البخار", "قدم السمك مع الخضار وشريحة ليمون"]),
         "السمك المشوي أصح من المقلي بكتير ومفيد للقلب"),

        ("M006", "دجاج مشوي مع أرز بني", "Grilled Chicken with Brown Rice", "lunch", "protein",
         json.dumps(["chicken breast", "brown rice", "mixed vegetables", "garlic"]),
         450, 38.0, 8.0, 50.0, 4.0, 120.0, 2.0, "35 min",
         "بروتين عالي مع كربوهيدرات معقدة", "High protein with complex carbs",
         json.dumps(["تبل صدور الفراخ بالتوم والبهارات", "اشوي الفراخ في الفرن 30 دقيقة", "اسلق الأرز البني", "سوتيه الخضار مع شوية زيت زيتون", "قدم الفراخ مع الأرز والخضار"]),
         "شيل الجلد من الفراخ عشان تقلل الدهون"),

        ("M007", "كشري مصري", "Egyptian Koshari", "lunch", "grains",
         json.dumps(["rice", "lentils", "macaroni", "tomato sauce", "onion", "garlic"]),
         550, 18.0, 7.0, 90.0, 8.0, 480.0, 12.0, "40 min",
         "وجبة مصرية تقليدية غنية بالطاقة", "Traditional Egyptian high-energy meal",
         json.dumps(["اسلق الأرز والعدس والمكرونة كل واحد لوحده", "حمر البصل لحد ما يبقى ذهبي ومقرمش", "اعمل صلصة طماطم بالتوم والخل", "رص الأرز والعدس والمكرونة في طبق", "ضيف الصلصة والبصل المحمر فوق"]),
         "الكشري وجبة مصرية كاملة غنية بالبروتين النباتي"),

        ("M008", "شوربة عدس", "Lentil Soup", "lunch", "soup",
         json.dumps(["red lentils", "carrot", "onion", "cumin", "lemon"]),
         250, 16.0, 3.0, 38.0, 11.0, 45.0, 4.0, "25 min",
         "غني بالألياف والبروتين النباتي", "Rich in fiber and plant protein",
         json.dumps(["اغسل العدس كويس", "سوتيه البصل والجزر المقطع", "ضيف العدس والمية واسلق 20 دقيقة", "اضرب في الخلاط لحد ما يبقى ناعم", "ضيف الكمون واعصر ليمونة فوقيه"]),
         "شوربة العدس مغذية جداً وسهلة في الهضم لكبار السن"),

        ("M009", "سلطة تونة", "Tuna Salad", "lunch", "protein",
         json.dumps(["tuna", "lettuce", "tomato", "cucumber", "olive oil", "lemon"]),
         280, 30.0, 12.0, 8.0, 3.0, 350.0, 2.0, "10 min",
         "غني بالبروتين والأوميجا 3", "Rich in protein and omega-3",
         json.dumps(["صفي التونة من الزيت كويس", "قطع الخس والطماطم والخيار", "اخلط الخضار مع التونة في طبق كبير", "ضيف زيت زيتون وعصير ليمون وقلب"]),
         "استخدم تونة في مية بدل الزيت لسعرات أقل"),

        # === DINNER ===
        ("M010", "سلطة دجاج مشوي", "Grilled Chicken Salad", "dinner", "salad",
         json.dumps(["chicken breast", "lettuce", "cucumber", "tomato", "olive oil"]),
         260, 28.0, 10.0, 8.0, 3.0, 85.0, 3.0, "20 min",
         "منخفض الكربوهيدرات", "Low carb",
         json.dumps(["اشوي صدور الفراخ واتبلها بالفلفل والليمون", "قطع الفراخ شرائح بعد ما تستوي", "قطع الخس والخيار والطماطم", "اخلط كل حاجة مع زيت زيتون"]),
         "ممكن تضيف شوية ليمون وأعشاب زي النعناع"),

        ("M011", "سمك مشوي بالأعشاب", "Herb-Grilled Fish", "dinner", "protein",
         json.dumps(["fish", "rosemary", "garlic", "lemon", "olive oil"]),
         290, 32.0, 12.0, 5.0, 1.0, 60.0, 1.0, "25 min",
         "بدون ملح، غني بالبوتاسيوم", "No salt, rich in potassium",
         json.dumps(["تبل السمك بالروزماري والتوم المفروم", "ضيف عصير ليمون وزيت زيتون", "لف السمك في ورق ألومنيوم", "اشوي في الفرن على 180 درجة لمدة 20 دقيقة"]),
         "الأعشاب بتدي نكهة حلوة من غير ما تحتاج ملح"),

        ("M012", "خضار مطبوخة على البخار", "Steamed Vegetables", "dinner", "vegetables",
         json.dumps(["broccoli", "carrot", "green beans", "zucchini"]),
         120, 5.0, 1.0, 20.0, 7.0, 35.0, 6.0, "15 min",
         "منخفض السعرات والصوديوم", "Low calorie and sodium",
         json.dumps(["قطع البروكلي والجزر والفاصوليا والكوسة", "حط الخضار في حلة البخار", "سيبها 10-15 دقيقة لحد ما تستوي", "قدمها مع شوية ليمون أو زيت زيتون"]),
         "خضار البخار بتحافظ على الفيتامينات أكتر من السلق"),

        ("M013", "شوربة خضار", "Vegetable Soup", "dinner", "soup",
         json.dumps(["carrot", "potato", "zucchini", "onion", "celery"]),
         150, 4.0, 2.0, 25.0, 5.0, 60.0, 7.0, "30 min",
         "وجبة خفيفة صحية", "Light healthy meal",
         json.dumps(["قطع الجزر والبطاطس والكوسة والبصل والكرفس", "سوتيه البصل في شوية زيت", "ضيف باقي الخضار والمية", "اسلق 25 دقيقة على نار هادية", "تبل بالملح القليل والفلفل"]),
         "ممكن تضربها في الخلاط لو حبيت شوربة ناعمة"),

        ("M014", "سلمون مشوي مع كركم", "Grilled Salmon with Turmeric", "dinner", "protein",
         json.dumps(["salmon", "turmeric", "ginger", "olive oil", "lemon"]),
         380, 34.0, 22.0, 3.0, 0.5, 70.0, 0.5, "20 min",
         "مضاد للالتهابات، غني بالأوميجا 3", "Anti-inflammatory, rich in omega-3",
         json.dumps(["اخلط الكركم والزنجبيل المبشور مع زيت الزيتون", "ادهن السلمون بالخليط من كل الجوانب", "اشوي في الفرن على 200 درجة لمدة 15 دقيقة", "اعصر ليمونة فوقيه وقدمه"]),
         "الكركم مضاد للالتهابات ومفيد جداً للمفاصل"),

        # === SNACK ===
        ("M015", "زبادي مع مكسرات", "Yogurt with Nuts", "snack", "dairy",
         json.dumps(["yogurt", "almonds", "walnuts", "honey"]),
         220, 10.0, 12.0, 18.0, 2.0, 55.0, 14.0, "5 min",
         "غني بالبروبيوتيك والدهون الصحية", "Rich in probiotics and healthy fats",
         json.dumps(["حط الزبادي في طبق", "ضيف اللوز والجوز فوقيه", "ضيف شوية عسل خفيف"]),
         "الزبادي غني بالبروبيوتيك المفيد للهضم"),

        ("M016", "فاكهة موسمية", "Seasonal Fruits", "snack", "fruits",
         json.dumps(["apple", "orange", "banana"]),
         150, 2.0, 0.5, 35.0, 4.0, 5.0, 25.0, "5 min",
         "فيتامينات وألياف طبيعية", "Natural vitamins and fiber",
         json.dumps(["اغسل الفاكهة كويس تحت المية", "قطع التفاح والبرتقال شرائح", "قدمها في طبق"]),
         "الفاكهة الطازجة أفضل من العصير عشان الألياف"),

        ("M017", "سلطة جمبري", "Shrimp Salad", "lunch", "protein",
         json.dumps(["shrimp", "lettuce", "avocado", "tomato", "lemon"]),
         300, 28.0, 14.0, 10.0, 4.0, 420.0, 2.0, "15 min",
         "غني بالبروتين", "Rich in protein",
         json.dumps(["اسلق الجمبري في مية مغلية 3 دقايق", "قطع الخس والأفوكادو والطماطم", "اخلط كل حاجة مع الجمبري", "ضيف عصير ليمون وزيت زيتون"]),
         "الجمبري غني بالبروتين وقليل الدهون"),

        ("M018", "ملوخية مع أرز", "Molokhia with Rice", "lunch", "vegetables",
         json.dumps(["molokhia", "rice", "chicken broth", "garlic", "coriander"]),
         380, 12.0, 8.0, 55.0, 5.0, 280.0, 3.0, "40 min",
         "وجبة مصرية تقليدية", "Traditional Egyptian meal",
         json.dumps(["سخن مرقة الفراخ", "ضيف الملوخية المفرومة وقلب", "في حلة تانية حمر التوم مع الكزبرة الناشفة", "ضيف التقلية على الملوخية وقلب", "قدمها مع الأرز الأبيض"]),
         "الملوخية مفيدة للهضم وغنية بالفيتامينات"),

        ("M019", "جريب فروت طازج", "Fresh Grapefruit", "snack", "fruits",
         json.dumps(["grapefruit"]),
         80, 1.5, 0.2, 18.0, 2.5, 0.0, 14.0, "5 min",
         "غني بفيتامين سي", "Rich in vitamin C",
         json.dumps(["اغسل الجريب فروت", "قطعه نصين", "كله بالمعلقة أو اعصره"]),
         "تحذير: الجريب فروت ممنوع مع بعض الأدوية - استشر طبيبك"),
    ]

    cursor.executemany("""
        INSERT OR IGNORE INTO meals 
        (meal_id, name_ar, name_en, meal_type, category, ingredients,
         energy_kcal, protein_g, fat_g, carbohydrate_g, fiber_g, sodium_mg, sugar_g,
         prep_time, notes_ar, notes_en, recipe_steps, recipe_tips)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, meals)


def _insert_condition_rules(cursor: sqlite3.Cursor):
    """Insert dietary rules per health condition."""
    rules = [
        ("R001", "diabetes",
         json.dumps(["sugar_g", "carbohydrate_g"]),
         json.dumps(["fiber_g", "protein_g"]),
         json.dumps(["sweets", "sugary drinks"]),
         json.dumps({"sugar_g": 10, "carbohydrate_g": 45})),

        ("R002", "hypertension",
         json.dumps(["sodium_mg"]),
         json.dumps(["fiber_g"]),
         json.dumps(["processed foods", "pickles"]),
         json.dumps({"sodium_mg": 200})),

        ("R003", "arthritis",
         json.dumps(["fat_g"]),
         json.dumps(["protein_g", "fiber_g"]),
         json.dumps(["fried foods"]),
         json.dumps({"fat_g": 20})),

        ("R004", "heart disease",
         json.dumps(["fat_g", "sodium_mg", "sugar_g"]),
         json.dumps(["fiber_g", "protein_g"]),
         json.dumps(["fried foods", "processed meats"]),
         json.dumps({"fat_g": 15, "sodium_mg": 150, "sugar_g": 12})),

        ("R005", "kidney disease",
         json.dumps(["sodium_mg", "protein_g"]),
         json.dumps(["carbohydrate_g"]),
         json.dumps(["high protein foods", "salty foods"]),
         json.dumps({"sodium_mg": 100, "protein_g": 20})),

        ("R006", "osteoporosis",
         json.dumps([]),
         json.dumps(["protein_g"]),
         json.dumps([]),
         json.dumps({})),
    ]

    cursor.executemany("""
        INSERT OR IGNORE INTO condition_dietary_rules
        (rule_id, condition, avoid_high, prefer_high, avoid_foods, max_values)
        VALUES (?, ?, ?, ?, ?, ?)
    """, rules)


def _insert_drug_food_interactions(cursor: sqlite3.Cursor):
    """Insert drug-food interaction records (from DDID patterns)."""
    interactions = [
        ("INT001", "metformin", "grapefruit", "negative", "moderate",
         "Grapefruit may affect metformin absorption and efficacy",
         "Avoid grapefruit and grapefruit juice while taking metformin"),

        ("INT002", "metformin", "alcohol", "negative", "severe",
         "Alcohol increases the risk of lactic acidosis with metformin",
         "Avoid alcohol consumption while taking metformin"),

        ("INT003", "lisinopril", "banana", "negative", "moderate",
         "Lisinopril increases potassium levels; bananas are high in potassium",
         "Limit high-potassium foods like bananas while taking lisinopril"),

        ("INT004", "lisinopril", "salt substitute", "negative", "severe",
         "Salt substitutes contain potassium which can cause dangerous hyperkalemia with ACE inhibitors",
         "Never use salt substitutes while taking lisinopril"),

        ("INT005", "warfarin", "spinach", "negative", "moderate",
         "Spinach is high in vitamin K which counteracts warfarin",
         "Maintain consistent vitamin K intake; avoid sudden increases in leafy greens"),

        ("INT006", "warfarin", "grapefruit", "negative", "moderate",
         "Grapefruit can increase warfarin levels and bleeding risk",
         "Avoid grapefruit while taking warfarin"),

        ("INT007", "warfarin", "garlic", "negative", "mild",
         "Garlic may increase the anticoagulant effect of warfarin",
         "Use garlic in moderation while on warfarin"),

        ("INT008", "simvastatin", "grapefruit", "negative", "severe",
         "Grapefruit significantly increases simvastatin levels causing muscle damage risk",
         "Completely avoid grapefruit and grapefruit juice with simvastatin"),

        ("INT009", "amlodipine", "grapefruit", "negative", "moderate",
         "Grapefruit may increase amlodipine blood levels",
         "Avoid grapefruit while taking amlodipine"),

        ("INT010", "metformin", "fiber", "positive", "mild",
         "High fiber foods help stabilize blood sugar alongside metformin",
         "Include high fiber foods in your diet"),

        ("INT011", "calcium", "spinach", "negative", "mild",
         "Oxalates in spinach can reduce calcium absorption",
         "Take calcium supplements separately from spinach-containing meals"),

        ("INT012", "levothyroxine", "coffee", "negative", "moderate",
         "Coffee can reduce levothyroxine absorption by up to 36%",
         "Take levothyroxine at least 30 minutes before coffee"),

        ("INT013", "ciprofloxacin", "milk", "negative", "moderate",
         "Dairy products reduce ciprofloxacin absorption",
         "Avoid dairy 2 hours before and after taking ciprofloxacin"),

        ("INT014", "aspirin", "alcohol", "negative", "severe",
         "Alcohol increases the risk of stomach bleeding with aspirin",
         "Avoid alcohol while taking aspirin"),

        ("INT015", "metformin", "carrot", "positive", "mild",
         "Carrots are low-glycemic and complement metformin therapy",
         "Carrots are a good food choice while on metformin"),

        ("INT016", "lisinopril", "fish", "positive", "mild",
         "Omega-3 in fish may complement blood pressure management",
         "Fish is a good dietary choice while on lisinopril"),

        ("INT017", "aspirin", "fish oil", "negative", "moderate",
         "Fish oil may increase bleeding risk when combined with aspirin",
         "Consult your doctor about fish oil supplements while on aspirin"),

        ("INT018", "metoprolol", "orange juice", "negative", "mild",
         "Orange juice may reduce metoprolol absorption",
         "Avoid orange juice close to metoprolol dosing time"),

        ("INT019", "diazepam", "grapefruit", "negative", "moderate",
         "Grapefruit increases diazepam levels causing excessive sedation",
         "Avoid grapefruit while taking diazepam"),

        ("INT020", "iron supplements", "coffee", "negative", "moderate",
         "Coffee tannins inhibit iron absorption by up to 60%",
         "Take iron supplements at least 1 hour before or 2 hours after coffee"),
    ]

    cursor.executemany("""
        INSERT OR IGNORE INTO drug_food_interactions
        (interaction_id, drug_name, food_name, effect, severity, conclusion, advice)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, interactions)


def _insert_disease_symptoms(cursor: sqlite3.Cursor):
    """Insert disease-symptom mappings with severity classification."""
    diseases = [
        # EMERGENCY severity
        ("DIS001", "stroke", json.dumps([
            "sudden severe headache", "face drooping", "arm weakness",
            "speech difficulty", "vision loss", "confusion", "dizziness",
            "loss of balance", "numbness"
        ]), "EMERGENCY",
         "A stroke occurs when blood supply to part of the brain is cut off"),

        ("DIS002", "heart attack", json.dumps([
            "chest pain", "chest pressure", "shortness of breath",
            "pain in left arm", "cold sweat", "nausea", "dizziness",
            "jaw pain", "fatigue"
        ]), "EMERGENCY",
         "A heart attack occurs when blood flow to the heart is blocked"),

        ("DIS003", "severe allergic reaction", json.dumps([
            "difficulty breathing", "swelling of throat", "swelling of face",
            "rapid heartbeat", "dizziness", "skin rash", "nausea",
            "low blood pressure"
        ]), "EMERGENCY",
         "Anaphylaxis is a severe, potentially life-threatening allergic reaction"),

        # URGENT severity
        ("DIS004", "pneumonia", json.dumps([
            "high fever", "cough", "difficulty breathing", "chest pain",
            "fatigue", "confusion", "chills", "sweating"
        ]), "URGENT",
         "Pneumonia is an infection that inflames the air sacs in the lungs"),

        ("DIS005", "deep vein thrombosis", json.dumps([
            "leg swelling", "leg pain", "warmth in leg", "redness in leg",
            "cramping"
        ]), "URGENT",
         "DVT is a blood clot in a deep vein, usually in the leg"),

        ("DIS006", "urinary tract infection", json.dumps([
            "burning urination", "frequent urination", "cloudy urine",
            "fever", "lower abdominal pain", "blood in urine"
        ]), "URGENT",
         "UTI is an infection in any part of the urinary system"),

        # MONITOR severity
        ("DIS007", "diabetes complications", json.dumps([
            "excessive thirst", "frequent urination", "blurry vision",
            "fatigue", "slow healing wounds", "tingling in hands",
            "tingling in feet", "weight loss"
        ]), "MONITOR",
         "Uncontrolled diabetes can lead to various complications"),

        ("DIS008", "hypertension crisis", json.dumps([
            "severe headache", "blurry vision", "dizziness", "nausea",
            "nosebleed", "shortness of breath", "chest pain"
        ]), "URGENT",
         "Hypertensive crisis occurs when blood pressure reaches dangerously high levels"),

        ("DIS009", "arthritis flare", json.dumps([
            "joint pain", "joint stiffness", "joint swelling", "reduced range of motion",
            "warmth around joint", "fatigue"
        ]), "MONITOR",
         "An arthritis flare is a period of increased disease activity"),

        ("DIS010", "gastroenteritis", json.dumps([
            "diarrhea", "nausea", "vomiting", "stomach cramps",
            "fever", "headache", "muscle aches"
        ]), "MONITOR",
         "Gastroenteritis is inflammation of the stomach and intestines"),

        # NORMAL severity
        ("DIS011", "common cold", json.dumps([
            "runny nose", "sneezing", "sore throat", "mild cough",
            "mild headache", "mild fever", "body aches"
        ]), "NORMAL",
         "The common cold is a viral infection of the upper respiratory tract"),

        ("DIS012", "seasonal allergy", json.dumps([
            "sneezing", "runny nose", "itchy eyes", "watery eyes",
            "nasal congestion", "itchy throat"
        ]), "NORMAL",
         "Seasonal allergies are immune responses to outdoor allergens"),

        ("DIS013", "mild dehydration", json.dumps([
            "dry mouth", "thirst", "dark urine", "fatigue",
            "dizziness", "headache"
        ]), "MONITOR",
         "Dehydration occurs when you use or lose more fluid than you take in"),

        ("DIS014", "insomnia", json.dumps([
            "difficulty sleeping", "waking up at night", "fatigue",
            "irritability", "difficulty concentrating", "daytime sleepiness"
        ]), "NORMAL",
         "Insomnia is a sleep disorder where you have trouble falling or staying asleep"),

        ("DIS015", "constipation", json.dumps([
            "infrequent bowel movements", "hard stools", "straining",
            "abdominal bloating", "abdominal pain", "feeling of incomplete evacuation"
        ]), "NORMAL",
         "Constipation is infrequent bowel movements or difficult passage of stools"),
    ]

    cursor.executemany("""
        INSERT OR IGNORE INTO disease_symptoms
        (disease_id, disease_name, symptoms, severity, description)
        VALUES (?, ?, ?, ?, ?)
    """, diseases)


def _insert_disease_precautions(cursor: sqlite3.Cursor):
    """Insert precautionary measures per disease."""
    precautions = [
        ("DIS001", "Call emergency services (123) immediately"),
        ("DIS001", "Do not give the person anything to eat or drink"),
        ("DIS001", "Note the time symptoms started"),
        ("DIS001", "Keep the person lying down with head slightly elevated"),

        ("DIS002", "Call emergency services (123) immediately"),
        ("DIS002", "Have the person chew an aspirin if not allergic"),
        ("DIS002", "Keep the person calm and lying down"),
        ("DIS002", "Loosen any tight clothing"),

        ("DIS003", "Call emergency services (123) immediately"),
        ("DIS003", "Use epinephrine auto-injector if available"),
        ("DIS003", "Lay the person flat with legs elevated"),

        ("DIS004", "Seek medical attention promptly"),
        ("DIS004", "Rest and drink plenty of fluids"),
        ("DIS004", "Monitor temperature regularly"),

        ("DIS005", "Seek immediate medical attention"),
        ("DIS005", "Do not massage the affected leg"),
        ("DIS005", "Keep the leg elevated"),

        ("DIS006", "Consult a doctor for antibiotics"),
        ("DIS006", "Drink plenty of water"),
        ("DIS006", "Avoid caffeine and alcohol"),

        ("DIS007", "Check blood sugar levels immediately"),
        ("DIS007", "Take prescribed diabetes medication"),
        ("DIS007", "Consult your doctor about adjusting treatment"),
        ("DIS007", "Stay hydrated"),

        ("DIS008", "Seek medical attention immediately"),
        ("DIS008", "Take prescribed blood pressure medication"),
        ("DIS008", "Rest in a quiet place"),
        ("DIS008", "Avoid salt and stress"),

        ("DIS009", "Rest the affected joints"),
        ("DIS009", "Apply warm or cold compresses"),
        ("DIS009", "Take prescribed anti-inflammatory medication"),

        ("DIS010", "Stay hydrated with clear fluids"),
        ("DIS010", "Eat bland foods when able"),
        ("DIS010", "Rest and avoid dairy products"),

        ("DIS011", "Rest and drink plenty of fluids"),
        ("DIS011", "Use over-the-counter cold remedies if appropriate"),
        ("DIS011", "Wash hands frequently to prevent spread"),

        ("DIS012", "Avoid known allergens"),
        ("DIS012", "Use antihistamines as directed"),
        ("DIS012", "Keep windows closed during high pollen days"),

        ("DIS013", "Drink water frequently"),
        ("DIS013", "Avoid caffeine and alcohol"),
        ("DIS013", "Eat water-rich fruits and vegetables"),

        ("DIS014", "Maintain a regular sleep schedule"),
        ("DIS014", "Avoid screens before bedtime"),
        ("DIS014", "Create a comfortable sleep environment"),

        ("DIS015", "Increase fiber intake gradually"),
        ("DIS015", "Drink plenty of water"),
        ("DIS015", "Exercise regularly"),
        ("DIS015", "Do not ignore the urge to have a bowel movement"),
    ]

    cursor.executemany("""
        INSERT INTO disease_precautions (disease_id, precaution)
        VALUES (?, ?)
    """, precautions)


def _insert_food_allergens(cursor: sqlite3.Cursor):
    """Insert food-to-allergen mappings."""
    allergens = [
        # Shellfish allergen
        ("shrimp", "shellfish"),
        ("crab", "shellfish"),
        ("lobster", "shellfish"),
        ("prawns", "shellfish"),

        # Dairy allergen
        ("milk", "dairy"),
        ("cheese", "dairy"),
        ("yogurt", "dairy"),
        ("cottage cheese", "dairy"),
        ("butter", "dairy"),

        # Gluten allergen
        ("whole wheat bread", "gluten"),
        ("bread", "gluten"),
        ("macaroni", "gluten"),
        ("oats", "gluten"),  # often contaminated

        # Nut allergen
        ("almonds", "nuts"),
        ("walnuts", "nuts"),
        ("peanuts", "nuts"),
        ("cashews", "nuts"),

        # Egg allergen
        ("eggs", "eggs"),

        # Fish allergen
        ("fish", "fish"),
        ("salmon", "fish"),
        ("tuna", "fish"),

        # Soy allergen
        ("soy sauce", "soy"),
        ("tofu", "soy"),
    ]

    cursor.executemany("""
        INSERT INTO food_allergens (food_name, allergen)
        VALUES (?, ?)
    """, allergens)


def _insert_medications(cursor: sqlite3.Cursor):
    """Insert sample medication schedules for test users."""
    medications = [
        # User 001 - Diabetes + Hypertension
        ("MED001", "user_001", "Metformin", "500mg",
         json.dumps(["08:00", "20:00"]),
         "للسكري", "For diabetes",
         "تناوله مع الطعام", "Take with food"),

        ("MED002", "user_001", "Lisinopril", "10mg",
         json.dumps(["09:00"]),
         "لضغط الدم", "For blood pressure",
         "تناوله في نفس الوقت يومياً", "Take at the same time daily"),

        # User 002 - Osteoporosis
        ("MED003", "user_002", "Calcium", "600mg",
         json.dumps(["08:00"]),
         "لصحة العظام", "For bone health",
         "تناوله مع الطعام", "Take with food"),

        ("MED004", "user_002", "Vitamin D", "1000IU",
         json.dumps(["08:00"]),
         "لامتصاص الكالسيوم", "For calcium absorption",
         "يمكن تناوله مع الكالسيوم", "Can be taken with calcium"),

        # User 003 - Heart Disease
        ("MED005", "user_003", "Aspirin", "81mg",
         json.dumps(["07:00"]),
         "لصحة القلب", "For heart health",
         "تناوله مع الطعام لحماية المعدة", "Take with food to protect stomach"),

        ("MED006", "user_003", "Simvastatin", "20mg",
         json.dumps(["21:00"]),
         "للكوليسترول", "For cholesterol",
         "تناوله في المساء", "Take in the evening"),

        ("MED007", "user_003", "Warfarin", "5mg",
         json.dumps(["18:00"]),
         "لسيولة الدم", "For blood thinning",
         "تناوله في نفس الوقت يومياً واحذر من فيتامين ك", "Take at same time daily, watch vitamin K intake"),

        # User 004 - Thyroid
        ("MED008", "user_004", "Levothyroxine", "50mcg",
         json.dumps(["06:00"]),
         "للغدة الدرقية", "For thyroid",
         "تناوله على معدة فارغة قبل الإفطار بـ30 دقيقة", "Take on empty stomach 30 min before breakfast"),
    ]

    cursor.executemany("""
        INSERT OR IGNORE INTO medications
        (med_id, user_id, name, dose, schedule, purpose_ar, purpose_en,
         instructions_ar, instructions_en)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, medications)


def _insert_exercises(cursor: sqlite3.Cursor):
    """Insert exercise recommendations by mobility level."""
    exercises = [
        # LIMITED mobility
        ("EX001", "تمارين التنفس العميق", "Deep Breathing Exercises", "limited", "seated",
         "5 دقائق", json.dumps([
             "اجلس بشكل مريح",
             "تنفس ببطء من الأنف لمدة 4 ثواني",
             "احبس النفس لمدة 4 ثواني",
             "أخرج النفس من الفم لمدة 6 ثواني",
             "كرر 5 مرات"
         ]),
         "يقلل التوتر ويحسن الأكسجين في الدم", "Reduces stress and improves blood oxygen",
         "توقف إذا شعرت بدوخة", "Stop if you feel dizzy",
         json.dumps([])),

        ("EX002", "تمارين الكاحل", "Ankle Circles", "limited", "seated",
         "3 دقائق", json.dumps([
             "اجلس على كرسي ثابت",
             "ارفع قدمك قليلاً عن الأرض",
             "أدر الكاحل في دوائر 10 مرات",
             "بدل الاتجاه",
             "كرر مع القدم الأخرى"
         ]),
         "يحسن الدورة الدموية في الساقين", "Improves blood circulation in legs",
         "لا تفرط في الحركة", "Do not overexert",
         json.dumps([])),

        ("EX003", "تمارين اليدين والأصابع", "Hand and Finger Exercises", "limited", "seated",
         "5 دقائق", json.dumps([
             "اجلس بشكل مريح",
             "افتح وأغلق يديك 10 مرات",
             "أدر معصميك في دوائر",
             "اضغط على كرة لينة إذا متاحة",
             "كرر 3 مجموعات"
         ]),
         "يحسن مرونة اليدين ويقلل تيبس المفاصل", "Improves hand flexibility and reduces joint stiffness",
         "توقف إذا شعرت بألم", "Stop if you feel pain",
         json.dumps(["arthritis"])),

        # MODERATE mobility
        ("EX004", "المشي في المكان", "Marching in Place", "moderate", "standing",
         "5 دقائق", json.dumps([
             "قف بجانب كرسي للاستناد",
             "ارفع ركبتك اليمنى",
             "أنزلها وارفع ركبتك اليسرى",
             "استمر ببطء لمدة 5 دقائق"
         ]),
         "يحسن اللياقة القلبية والتوازن", "Improves cardiovascular fitness and balance",
         "استخدم الكرسي للتوازن", "Use chair for balance",
         json.dumps([])),

        ("EX005", "تمارين رفع الذراعين", "Arm Raises", "moderate", "standing",
         "3 دقائق", json.dumps([
             "قف أو اجلس بشكل مستقيم",
             "ارفع ذراعيك للأمام ببطء",
             "ارفعهما فوق رأسك",
             "أنزلهما ببطء",
             "كرر 10 مرات"
         ]),
         "يقوي عضلات الكتف والذراع", "Strengthens shoulder and arm muscles",
         "لا ترفع أعلى من راحتك", "Don't raise higher than comfortable",
         json.dumps([])),

        ("EX006", "تمارين القرفصاء الخفيفة", "Light Squats", "moderate", "standing",
         "5 دقائق", json.dumps([
             "قف خلف كرسي ثابت",
             "امسك ظهر الكرسي بكلتا يديك",
             "انزل ببطء كأنك تجلس",
             "قف مرة أخرى",
             "كرر 8 مرات"
         ]),
         "يقوي عضلات الساقين", "Strengthens leg muscles",
         "لا تنزل أكثر من 90 درجة", "Don't go lower than 90 degrees",
         json.dumps(["arthritis", "knee injury"])),

        # GOOD mobility
        ("EX007", "المشي الخفيف", "Light Walking", "good", "walking",
         "15-20 دقيقة", json.dumps([
             "اختر مكاناً مستوياً وآمناً",
             "امشِ بخطوات ثابتة",
             "حافظ على وتيرة مريحة",
             "استرح كل 5 دقائق إذا لزم الأمر"
         ]),
         "يحسن صحة القلب والمزاج", "Improves heart health and mood",
         "تجنب الأسطح غير المستوية", "Avoid uneven surfaces",
         json.dumps([])),

        ("EX008", "تمارين التوازن", "Balance Exercises", "good", "standing",
         "10 دقائق", json.dumps([
             "قف بجانب حائط أو كرسي للأمان",
             "ارفع قدماً واحدة لمدة 10 ثوانٍ",
             "بدل إلى القدم الأخرى",
             "كرر 5 مرات لكل قدم",
             "حاول زيادة المدة تدريجياً"
         ]),
         "يقلل خطر السقوط ويحسن الثبات", "Reduces fall risk and improves stability",
         "احتفظ دائماً بشيء تستند إليه قريباً", "Always keep something to hold nearby",
         json.dumps([])),
    ]

    cursor.executemany("""
        INSERT OR IGNORE INTO exercises
        (exercise_id, name_ar, name_en, mobility_level, exercise_type, duration,
         steps, benefits_ar, benefits_en, safety_ar, safety_en, avoid_conditions)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, exercises)


def reset_database():
    """Delete and recreate the database. Useful for testing."""
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    # Also remove WAL/SHM files if they exist
    for ext in ["-wal", "-shm"]:
        path = DB_PATH + ext
        if os.path.exists(path):
            os.remove(path)
    _initialize_database()
