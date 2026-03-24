"""
Начальные данные платформы: навыки и теги.

Запускается через Alembic data migration или отдельной командой.
Стартовый список составлен на основе анализа популярных IT-специальностей
(Python-разработка, Frontend, DevOps, Data Science, Mobile и т.д.)
"""

from typing import Any

from src.models.enums import SkillCategory

# ──────────────────────────────────────────────────────────────
#  НАВЫКИ (Skills) — технологии и инструменты
# ──────────────────────────────────────────────────────────────

INITIAL_SKILLS: list[dict[str, str | SkillCategory]] = [
    # Языки программирования
    {"name": "Python", "slug": "python", "category": SkillCategory.LANGUAGE},
    {"name": "JavaScript", "slug": "javascript", "category": SkillCategory.LANGUAGE},
    {"name": "TypeScript", "slug": "typescript", "category": SkillCategory.LANGUAGE},
    {"name": "Java", "slug": "java", "category": SkillCategory.LANGUAGE},
    {"name": "Kotlin", "slug": "kotlin", "category": SkillCategory.LANGUAGE},
    {"name": "Swift", "slug": "swift", "category": SkillCategory.LANGUAGE},
    {"name": "Go", "slug": "go", "category": SkillCategory.LANGUAGE},
    {"name": "Rust", "slug": "rust", "category": SkillCategory.LANGUAGE},
    {"name": "C++", "slug": "cpp", "category": SkillCategory.LANGUAGE},
    {"name": "C#", "slug": "csharp", "category": SkillCategory.LANGUAGE},
    {"name": "PHP", "slug": "php", "category": SkillCategory.LANGUAGE},
    {"name": "Ruby", "slug": "ruby", "category": SkillCategory.LANGUAGE},
    {"name": "Scala", "slug": "scala", "category": SkillCategory.LANGUAGE},
    # Backend фреймворки
    {"name": "FastAPI", "slug": "fastapi", "category": SkillCategory.FRAMEWORK},
    {"name": "Django", "slug": "django", "category": SkillCategory.FRAMEWORK},
    {"name": "Flask", "slug": "flask", "category": SkillCategory.FRAMEWORK},
    {"name": "Spring Boot", "slug": "spring-boot", "category": SkillCategory.FRAMEWORK},
    {"name": "Node.js", "slug": "nodejs", "category": SkillCategory.FRAMEWORK},
    {"name": "NestJS", "slug": "nestjs", "category": SkillCategory.FRAMEWORK},
    {"name": "Express.js", "slug": "expressjs", "category": SkillCategory.FRAMEWORK},
    {"name": "Laravel", "slug": "laravel", "category": SkillCategory.FRAMEWORK},
    # Frontend фреймворки
    {"name": "React", "slug": "react", "category": SkillCategory.FRAMEWORK},
    {"name": "Vue.js", "slug": "vuejs", "category": SkillCategory.FRAMEWORK},
    {"name": "Angular", "slug": "angular", "category": SkillCategory.FRAMEWORK},
    {"name": "Next.js", "slug": "nextjs", "category": SkillCategory.FRAMEWORK},
    {"name": "Svelte", "slug": "svelte", "category": SkillCategory.FRAMEWORK},
    # Мобильная разработка
    {"name": "React Native", "slug": "react-native", "category": SkillCategory.MOBILE},
    {"name": "Flutter", "slug": "flutter", "category": SkillCategory.MOBILE},
    {"name": "Android SDK", "slug": "android-sdk", "category": SkillCategory.MOBILE},
    {"name": "iOS UIKit", "slug": "ios-uikit", "category": SkillCategory.MOBILE},
    {"name": "SwiftUI", "slug": "swiftui", "category": SkillCategory.MOBILE},
    # Базы данных
    {"name": "PostgreSQL", "slug": "postgresql", "category": SkillCategory.DATABASE},
    {"name": "MySQL", "slug": "mysql", "category": SkillCategory.DATABASE},
    {"name": "MongoDB", "slug": "mongodb", "category": SkillCategory.DATABASE},
    {"name": "Redis", "slug": "redis", "category": SkillCategory.DATABASE},
    {"name": "Elasticsearch", "slug": "elasticsearch", "category": SkillCategory.DATABASE},
    {"name": "ClickHouse", "slug": "clickhouse", "category": SkillCategory.DATABASE},
    {"name": "Cassandra", "slug": "cassandra", "category": SkillCategory.DATABASE},
    {"name": "SQL", "slug": "sql", "category": SkillCategory.DATABASE},
    # DevOps
    {"name": "Docker", "slug": "docker", "category": SkillCategory.DEVOPS},
    {"name": "Kubernetes", "slug": "kubernetes", "category": SkillCategory.DEVOPS},
    {"name": "CI/CD", "slug": "ci-cd", "category": SkillCategory.DEVOPS},
    {"name": "GitHub Actions", "slug": "github-actions", "category": SkillCategory.DEVOPS},
    {"name": "GitLab CI", "slug": "gitlab-ci", "category": SkillCategory.DEVOPS},
    {"name": "Terraform", "slug": "terraform", "category": SkillCategory.DEVOPS},
    {"name": "Ansible", "slug": "ansible", "category": SkillCategory.DEVOPS},
    {"name": "Nginx", "slug": "nginx", "category": SkillCategory.DEVOPS},
    {"name": "Linux", "slug": "linux", "category": SkillCategory.DEVOPS},
    # Облака
    {"name": "AWS", "slug": "aws", "category": SkillCategory.CLOUD},
    {"name": "Google Cloud", "slug": "gcp", "category": SkillCategory.CLOUD},
    {"name": "Azure", "slug": "azure", "category": SkillCategory.CLOUD},
    {"name": "Yandex Cloud", "slug": "yandex-cloud", "category": SkillCategory.CLOUD},
    # AI/ML
    {"name": "PyTorch", "slug": "pytorch", "category": SkillCategory.AI_ML},
    {"name": "TensorFlow", "slug": "tensorflow", "category": SkillCategory.AI_ML},
    {"name": "scikit-learn", "slug": "scikit-learn", "category": SkillCategory.AI_ML},
    {"name": "Pandas", "slug": "pandas", "category": SkillCategory.AI_ML},
    {"name": "NumPy", "slug": "numpy", "category": SkillCategory.AI_ML},
    {"name": "LangChain", "slug": "langchain", "category": SkillCategory.AI_ML},
    {"name": "Hugging Face", "slug": "huggingface", "category": SkillCategory.AI_ML},
    # Дизайн
    {"name": "Figma", "slug": "figma", "category": SkillCategory.DESIGN},
    {"name": "Adobe XD", "slug": "adobe-xd", "category": SkillCategory.DESIGN},
    # Управление
    {"name": "Scrum", "slug": "scrum", "category": SkillCategory.MANAGEMENT},
    {"name": "Agile", "slug": "agile", "category": SkillCategory.MANAGEMENT},
    {"name": "Kanban", "slug": "kanban", "category": SkillCategory.MANAGEMENT},
    # Прочее
    {"name": "Git", "slug": "git", "category": SkillCategory.OTHER},
    {"name": "REST API", "slug": "rest-api", "category": SkillCategory.OTHER},
    {"name": "GraphQL", "slug": "graphql", "category": SkillCategory.OTHER},
    {"name": "gRPC", "slug": "grpc", "category": SkillCategory.OTHER},
    {"name": "WebSocket", "slug": "websocket", "category": SkillCategory.OTHER},
    {"name": "RabbitMQ", "slug": "rabbitmq", "category": SkillCategory.OTHER},
    {"name": "Kafka", "slug": "kafka", "category": SkillCategory.OTHER},
]

# ──────────────────────────────────────────────────────────────
#  ТЕГИ (Tags) — уровни, форматы, специализации
# ──────────────────────────────────────────────────────────────

INITIAL_TAGS: list[dict[str, str | None]] = [
    # Уровень опыта
    {"name": "Intern", "slug": "intern", "category": "level", "color": "#6EE7B7"},
    {"name": "Junior", "slug": "junior", "category": "level", "color": "#34D399"},
    {"name": "Middle", "slug": "middle", "category": "level", "color": "#F59E0B"},
    {"name": "Senior", "slug": "senior", "category": "level", "color": "#EF4444"},
    {"name": "Lead", "slug": "lead", "category": "level", "color": "#8B5CF6"},
    # Тип занятости
    {"name": "Полная занятость", "slug": "full-time", "category": "employment"},
    {"name": "Частичная занятость", "slug": "part-time", "category": "employment"},
    {"name": "Проектная работа", "slug": "project", "category": "employment"},
    {"name": "Волонтёрство", "slug": "volunteer", "category": "employment"},
    # Направления
    {"name": "Backend", "slug": "backend", "category": "direction", "color": "#3B82F6"},
    {"name": "Frontend", "slug": "frontend", "category": "direction", "color": "#EC4899"},
    {"name": "Fullstack", "slug": "fullstack", "category": "direction", "color": "#8B5CF6"},
    {"name": "Mobile", "slug": "mobile", "category": "direction", "color": "#F97316"},
    {"name": "DevOps", "slug": "devops", "category": "direction", "color": "#14B8A6"},
    {"name": "Data Science", "slug": "data-science", "category": "direction", "color": "#6366F1"},
    {"name": "ML Engineer", "slug": "ml-engineer", "category": "direction"},
    {"name": "QA / Testing", "slug": "qa", "category": "direction", "color": "#84CC16"},
    {"name": "UX/UI Design", "slug": "ux-ui", "category": "direction", "color": "#F43F5E"},
    {"name": "Product Manager", "slug": "product-manager", "category": "direction"},
    {"name": "Аналитик данных", "slug": "data-analyst", "category": "direction"},
    {"name": "Системный аналитик", "slug": "systems-analyst", "category": "direction"},
    {"name": "Gamedev", "slug": "gamedev", "category": "direction"},
    {"name": "Кибербезопасность", "slug": "cybersecurity", "category": "direction"},
    {"name": "Embedded / IoT", "slug": "embedded", "category": "direction"},
    # Особые теги
    {"name": "Для студентов", "slug": "for-students", "category": "special", "color": "#06B6D4"},
    {"name": "Без опыта", "slug": "no-experience", "category": "special", "color": "#10B981"},
    {"name": "Стипендия", "slug": "stipend", "category": "special"},
    {"name": "Релокация", "slug": "relocation", "category": "special"},
    {"name": "Наставник предоставляется", "slug": "mentor-provided", "category": "special"},
    {"name": "Хакатон", "slug": "hackathon", "category": "event_type"},
    {"name": "День открытых дверей", "slug": "open-day", "category": "event_type"},
    {"name": "Лекция", "slug": "lecture", "category": "event_type"},
    {"name": "Воркшоп", "slug": "workshop", "category": "event_type"},
    {"name": "Карьерная ярмарка", "slug": "career-fair", "category": "event_type"},
]


async def seed_skills_and_tags(session: Any) -> None:  # noqa: ANN401
    """Заполняет каталоги навыков и тегов начальными системными данными."""
    from sqlalchemy import select

    from src.models.opportunity import Tag
    from src.models.skill import Skill

    # Навыки
    for skill_data in INITIAL_SKILLS:
        exists = await session.scalar(select(Skill.id).where(Skill.slug == skill_data["slug"]))
        if not exists:
            session.add(
                Skill(
                    name=skill_data["name"],
                    slug=skill_data["slug"],
                    category=skill_data["category"],
                    is_system=True,
                    is_approved=True,
                )
            )

    # Теги
    for tag_data in INITIAL_TAGS:
        exists = await session.scalar(select(Tag.id).where(Tag.slug == tag_data["slug"]))
        if not exists:
            session.add(
                Tag(
                    name=tag_data["name"],
                    slug=tag_data["slug"],
                    category=tag_data.get("category"),
                    color=tag_data.get("color"),
                    is_system=True,
                    is_approved=True,
                )
            )

    await session.commit()
