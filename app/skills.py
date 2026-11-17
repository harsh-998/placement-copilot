"""Skill taxonomy, learning resources and a fallback interview question bank.

Used by agents for deterministic extraction/matching, and as the offline fallback.
"""
import re
from urllib.parse import quote_plus

# canonical skill -> (category, aliases)
TAXONOMY = {
    # Languages
    "Python": ("Language", ["python"]),
    "Java": ("Language", ["java"]),
    "JavaScript": ("Language", ["javascript", "js", "es6"]),
    "TypeScript": ("Language", ["typescript", "ts"]),
    "C++": ("Language", ["c\\+\\+", "cpp"]),
    "C": ("Language", ["c programming", "c language"]),
    "Go": ("Language", ["golang", "go lang"]),
    "Kotlin": ("Language", ["kotlin"]),
    "SQL": ("Database", ["sql"]),
    # Frontend
    "HTML": ("Frontend", ["html", "html5"]),
    "CSS": ("Frontend", ["css", "css3", "scss", "sass"]),
    "React": ("Frontend", ["react", "react\\.js", "reactjs"]),
    "Next.js": ("Frontend", ["next\\.js", "nextjs"]),
    "Angular": ("Frontend", ["angular"]),
    "Vue": ("Frontend", ["vue", "vue\\.js"]),
    "Tailwind CSS": ("Frontend", ["tailwind", "tailwindcss"]),
    "Redux": ("Frontend", ["redux"]),
    # Backend
    "Node.js": ("Backend", ["node", "node\\.js", "nodejs"]),
    "Express": ("Backend", ["express", "express\\.js", "expressjs"]),
    "Django": ("Backend", ["django"]),
    "Flask": ("Backend", ["flask"]),
    "FastAPI": ("Backend", ["fastapi"]),
    "Spring Boot": ("Backend", ["spring boot", "springboot"]),
    "REST APIs": ("Backend", ["restful", "rest api", "rest apis", "rest-api"]),
    "GraphQL": ("Backend", ["graphql"]),
    "Microservices": ("Backend", ["microservices", "microservice"]),
    "WebSockets": ("Backend", ["websocket", "websockets", "socket\\.io", "webrtc"]),
    # Databases
    "MySQL": ("Database", ["mysql"]),
    "PostgreSQL": ("Database", ["postgresql", "postgres"]),
    "MongoDB": ("Database", ["mongodb", "mongo"]),
    "Redis": ("Database", ["redis"]),
    "Firebase": ("Database", ["firebase", "firestore"]),
    # DevOps / Cloud
    "Git": ("DevOps", ["git", "github", "gitlab"]),
    "Docker": ("DevOps", ["docker", "containers"]),
    "Kubernetes": ("DevOps", ["kubernetes", "k8s"]),
    "CI/CD": ("DevOps", ["ci/cd", "ci cd", "github actions", "jenkins", "continuous integration"]),
    "Linux": ("DevOps", ["linux", "bash", "shell scripting"]),
    "AWS": ("Cloud", ["aws", "amazon web services", "ec2", "s3", "lambda"]),
    "Azure": ("Cloud", ["azure"]),
    "GCP": ("Cloud", ["gcp", "google cloud"]),
    "Terraform": ("DevOps", ["terraform"]),
    # Data / ML
    "Machine Learning": ("AI/ML", ["machine learning", "ml"]),
    "Deep Learning": ("AI/ML", ["deep learning", "neural network", "neural networks", "cnn", "rnn"]),
    "NLP": ("AI/ML", ["nlp", "natural language processing"]),
    "Computer Vision": ("AI/ML", ["computer vision", "opencv", "yolo", "yolov8", "object detection", "ocr"]),
    "TensorFlow": ("AI/ML", ["tensorflow", "keras"]),
    "PyTorch": ("AI/ML", ["pytorch", "torch"]),
    "scikit-learn": ("AI/ML", ["scikit-learn", "sklearn", "scikit learn"]),
    "Pandas": ("Data", ["pandas"]),
    "NumPy": ("Data", ["numpy"]),
    "Data Visualization": ("Data", ["matplotlib", "seaborn", "data visualization", "plotly"]),
    "Power BI": ("Data", ["power bi", "powerbi"]),
    "Tableau": ("Data", ["tableau"]),
    "Excel": ("Data", ["excel", "spreadsheets"]),
    "Statistics": ("Data", ["statistics", "statistical", "hypothesis testing"]),
    "LLMs": ("AI/ML", ["llm", "llms", "large language model", "gpt", "langchain", "rag", "prompt engineering", "generative ai", "genai"]),
    # CS fundamentals
    "Data Structures": ("CS Fundamentals", ["data structures", "dsa"]),
    "Algorithms": ("CS Fundamentals", ["algorithms", "algorithm", "dsa"]),
    "OOP": ("CS Fundamentals", ["oop", "object oriented", "object-oriented"]),
    "DBMS": ("CS Fundamentals", ["dbms", "database management", "normalization"]),
    "Operating Systems": ("CS Fundamentals", ["operating systems", "operating system"]),
    "Computer Networks": ("CS Fundamentals", ["computer networks", "networking", "tcp/ip"]),
    "System Design": ("CS Fundamentals", ["system design", "scalability", "distributed systems"]),
    # Mobile / testing / other
    "Android": ("Mobile", ["android"]),
    "Flutter": ("Mobile", ["flutter", "dart"]),
    "React Native": ("Mobile", ["react native"]),
    "Unit Testing": ("Testing", ["unit testing", "jest", "pytest", "junit", "testing"]),
    "Selenium": ("Testing", ["selenium", "test automation", "cypress", "playwright"]),
    "Agile": ("Process", ["agile", "scrum", "jira"]),
    "Figma": ("Design", ["figma"]),
    "Communication": ("Soft Skill", ["communication", "presentation skills"]),
    "Leadership": ("Soft Skill", ["leadership", "led a team", "team lead", "technical lead", "product lead"]),
    "Problem Solving": ("Soft Skill", ["problem solving", "problem-solving", "leetcode", "codeforces", "codechef"]),
}

_PATTERNS = {
    skill: re.compile(r"(?<![a-z0-9])(" + "|".join(aliases) + r")(?![a-z0-9])", re.I)
    for skill, (_, aliases) in TAXONOMY.items()
}

# Words that are too ambiguous to trust in a resume (e.g. "go", "c", "lead").
_AMBIGUOUS = {"Go": re.compile(r"(?<![a-z])(golang|go lang)(?![a-z])", re.I)}


def extract_skills(text: str) -> list[str]:
    found = []
    for skill, pat in _PATTERNS.items():
        if skill in _AMBIGUOUS:
            if _AMBIGUOUS[skill].search(text):
                found.append(skill)
        elif pat.search(text):
            found.append(skill)
    return found


def category(skill: str) -> str:
    return TAXONOMY.get(canonical(skill), ("Other", []))[0]


def canonical(skill: str) -> str:
    s = skill.strip()
    for name in TAXONOMY:
        if name.lower() == s.lower():
            return name
    hits = extract_skills(s)
    return hits[0] if len(hits) == 1 else s


def norm_set(skills) -> set[str]:
    return {canonical(s).lower() for s in skills if s}


# Free, well-known learning resources. Anything not listed gets search links.
RESOURCES = {
    "Python": [("Python official tutorial", "https://docs.python.org/3/tutorial/")],
    "JavaScript": [("MDN JavaScript Guide", "https://developer.mozilla.org/en-US/docs/Web/JavaScript/Guide")],
    "TypeScript": [("TypeScript Handbook", "https://www.typescriptlang.org/docs/handbook/intro.html")],
    "React": [("React docs – Learn", "https://react.dev/learn")],
    "Next.js": [("Next.js Learn course", "https://nextjs.org/learn")],
    "Node.js": [("Node.js – Learn", "https://nodejs.org/en/learn")],
    "Express": [("Express guide", "https://expressjs.com/en/guide/routing.html")],
    "HTML": [("MDN – HTML basics", "https://developer.mozilla.org/en-US/docs/Learn/HTML")],
    "CSS": [("MDN – CSS", "https://developer.mozilla.org/en-US/docs/Learn/CSS")],
    "SQL": [("SQLBolt interactive lessons", "https://sqlbolt.com/")],
    "PostgreSQL": [("PostgreSQL tutorial (official)", "https://www.postgresql.org/docs/current/tutorial.html")],
    "MongoDB": [("MongoDB University", "https://learn.mongodb.com/")],
    "Docker": [("Docker – Get started", "https://docs.docker.com/get-started/")],
    "Kubernetes": [("Kubernetes basics tutorial", "https://kubernetes.io/docs/tutorials/kubernetes-basics/")],
    "Git": [("Pro Git book", "https://git-scm.com/book/en/v2")],
    "AWS": [("AWS Skill Builder", "https://skillbuilder.aws/")],
    "Machine Learning": [("Google ML Crash Course", "https://developers.google.com/machine-learning/crash-course")],
    "Deep Learning": [("fast.ai Practical Deep Learning", "https://course.fast.ai/")],
    "PyTorch": [("PyTorch tutorials", "https://pytorch.org/tutorials/")],
    "TensorFlow": [("TensorFlow tutorials", "https://www.tensorflow.org/tutorials")],
    "scikit-learn": [("scikit-learn user guide", "https://scikit-learn.org/stable/user_guide.html")],
    "Pandas": [("pandas getting started", "https://pandas.pydata.org/docs/getting_started/index.html")],
    "Data Structures": [("NeetCode roadmap", "https://neetcode.io/roadmap")],
    "Algorithms": [("NeetCode roadmap", "https://neetcode.io/roadmap")],
    "System Design": [("System Design Primer", "https://github.com/donnemartin/system-design-primer")],
    "REST APIs": [("MDN – HTTP overview", "https://developer.mozilla.org/en-US/docs/Web/HTTP/Overview")],
    "GraphQL": [("GraphQL – Learn", "https://graphql.org/learn/")],
    "Linux": [("Linux Journey", "https://linuxjourney.com/")],
    "CI/CD": [("GitHub Actions docs", "https://docs.github.com/en/actions")],
    "FastAPI": [("FastAPI tutorial", "https://fastapi.tiangolo.com/tutorial/")],
    "Django": [("Django tutorial", "https://docs.djangoproject.com/en/stable/intro/tutorial01/")],
    "Spring Boot": [("Spring guides", "https://spring.io/guides")],
    "Tailwind CSS": [("Tailwind docs", "https://tailwindcss.com/docs")],
    "Redis": [("Redis University", "https://university.redis.io/")],
    "LLMs": [("Hugging Face LLM course", "https://huggingface.co/learn/llm-course")],
    "Flutter": [("Flutter – Get started", "https://docs.flutter.dev/get-started")],
    "Android": [("Android Basics with Compose", "https://developer.android.com/courses/android-basics-compose/course")],
}


def resources_for(skill: str) -> list[dict]:
    items = [{"title": t, "url": u} for t, u in RESOURCES.get(canonical(skill), [])]
    q = quote_plus(f"{skill} tutorial for beginners")
    items.append({"title": f"{skill} – video tutorials", "url": f"https://www.youtube.com/results?search_query={q}"})
    if len(items) < 2:
        items.append({"title": f"{skill} – search docs", "url": f"https://www.google.com/search?q={quote_plus(skill + ' documentation')}"})
    return items


# Fallback interview bank: (topic, question, expected keywords)
TECH_BANK = {
    "Python": [
        ("Python", "What is the difference between a list and a tuple in Python, and when would you use each?", ["mutable", "immutable", "hashable", "performance"]),
        ("Python", "Explain how Python decorators work with an example use case.", ["function", "wrapper", "closure", "@"]),
    ],
    "JavaScript": [
        ("JavaScript", "Explain the event loop in JavaScript.", ["call stack", "queue", "microtask", "asynchronous"]),
        ("JavaScript", "What is a closure and where have you used one?", ["scope", "function", "outer", "variable"]),
    ],
    "React": [
        ("React", "How does React decide when to re-render a component?", ["state", "props", "virtual dom", "reconciliation"]),
        ("React", "When would you use useMemo or useCallback?", ["memoize", "performance", "dependency", "re-render"]),
    ],
    "Node.js": [
        ("Node.js", "How does Node.js handle many concurrent requests on a single thread?", ["event loop", "non-blocking", "libuv", "asynchronous"]),
    ],
    "SQL": [
        ("SQL", "What is the difference between INNER JOIN and LEFT JOIN?", ["matching", "null", "all rows", "left table"]),
        ("SQL", "How would you find the second highest salary in a table?", ["order by", "limit", "offset", "subquery", "dense_rank"]),
    ],
    "DBMS": [("DBMS", "Explain database normalization and why it matters.", ["redundancy", "1nf", "2nf", "3nf", "anomal"])],
    "Data Structures": [
        ("Data Structures", "When would you choose a hash map over a balanced BST?", ["o(1)", "ordered", "log n", "collision"]),
        ("Data Structures", "How would you detect a cycle in a linked list?", ["fast", "slow", "pointer", "floyd"]),
    ],
    "Algorithms": [("Algorithms", "Explain the difference between BFS and DFS and a use case for each.", ["queue", "stack", "shortest path", "recursion"])],
    "OOP": [("OOP", "Explain the four pillars of OOP with examples.", ["encapsulation", "inheritance", "polymorphism", "abstraction"])],
    "Docker": [("Docker", "What is the difference between a Docker image and a container?", ["template", "instance", "layers", "running"])],
    "Git": [("Git", "What is the difference between git merge and git rebase?", ["history", "linear", "commit", "conflict"])],
    "REST APIs": [("REST APIs", "What makes an API RESTful? Explain idempotency.", ["stateless", "resource", "http methods", "idempotent", "put"])],
    "Machine Learning": [
        ("Machine Learning", "Explain overfitting and how you would prevent it.", ["training", "generalize", "regularization", "validation", "dropout"]),
        ("Machine Learning", "What is the difference between precision and recall?", ["false positive", "false negative", "f1", "threshold"]),
    ],
    "Operating Systems": [("Operating Systems", "What is the difference between a process and a thread?", ["memory", "shared", "context switch", "lightweight"])],
    "Computer Networks": [("Computer Networks", "What happens when you type a URL into the browser?", ["dns", "tcp", "http", "handshake", "render"])],
    "System Design": [("System Design", "How would you design a URL shortener?", ["hash", "database", "cache", "scale", "redirect"])],
    "Java": [("Java", "What is the difference between an interface and an abstract class in Java?", ["implement", "extend", "multiple", "default"])],
    "MongoDB": [("MongoDB", "When would you choose MongoDB over a relational database?", ["schema", "document", "flexible", "joins", "scale"])],
}

HR_BANK = [
    ("Introduction", "Tell me about yourself.", ["background", "project", "skills", "goal"]),
    ("Motivation", "Why do you want to work at our company in this role?", ["role", "learn", "contribute", "product"]),
    ("Teamwork", "Describe a time you had a conflict in a team and how you resolved it.", ["situation", "action", "result", "listen"]),
    ("Ownership", "Tell me about a project you are most proud of and your exact contribution.", ["built", "impact", "result", "challenge"]),
    ("Failure", "Describe a failure and what you learned from it.", ["mistake", "learned", "improve", "result"]),
    ("Goals", "Where do you see yourself in three years?", ["grow", "skills", "responsibility", "learn"]),
]
