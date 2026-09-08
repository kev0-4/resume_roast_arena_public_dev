"""
Evaluation resume fixtures for the LLM quality-scoring feature.

Content provenance: bullet points are drawn from / closely modeled on
publicly-published teaching examples (rejectless.app's SWE bullet guide,
generic quant/HFT resume-writing guides, generic IB resume-writing guides)
-- explicitly published as reference material for anyone to study, not
scraped from any identifiable individual's personal resume or private
"please review my resume" post. No real names, companies, or contact
info. Bullets are remixed into synthetic composite resumes (a "resume
shape" built from several sources' bullets), not a reproduction of any
single real document.

Three tiers x three verticals (SWE/FAANG, Quant/HFT, IB), plus mid and
bad tiers built from genuinely mediocre/weak phrasing (the "weak" side
of the same before/after pairs the strong-tier bullets came from, so the
contrast is apples-to-apples, not a strawman).
"""

TOP_TIER = {
    "faang_backend_1": {
        "vertical": "SWE",
        "experience": [
            {"text": (
                "Senior Software Engineer, Backend Platform -- 2021-Present\n"
                "- Optimized 14 slow PostgreSQL queries identified via pg_stat_statements, adding partial indexes and rewriting N+1 patterns, cutting average API response time from 800ms to 95ms\n"
                "- Built an event-driven data pipeline using Kafka and Apache Flink processing 2.8B events/day, replacing batch ETL and reducing data freshness latency from 6 hours to under 90 seconds\n"
                "- Introduced a two-tier caching strategy (local Caffeine + distributed Redis) for the recommendation engine, reducing compute costs by $12K/month\n"
                "- Migrated 380K user accounts from legacy session-based auth to OAuth 2.0 + PKCE flow using Auth0, achieving zero-downtime cutover and reducing support tickets by 74%"
            )},
        ],
        "projects": [{"text": "Contributed 14 merged PRs to Apache Kafka (Java), including a fix for a partition reassignment race condition affecting clusters with 500+ partitions."}],
        "skills": [{"text": "Java, Go, Kafka, Flink, PostgreSQL, Redis, AWS, Terraform"}],
    },
    "faang_frontend_1": {
        "vertical": "SWE",
        "experience": [
            {"text": (
                "Software Engineer, Web Platform -- 2020-Present\n"
                "- Reduced initial bundle size from 2.4MB to 380KB through code splitting, tree shaking, and lazy-loading 14 route-level components, cutting Time to Interactive from 6.2s to 1.8s\n"
                "- Created a shared component library of 45 accessible React components (WCAG 2.1 AA) with Storybook documentation, adopted across 4 product teams\n"
                "- Redesigned the 5-step checkout flow into a single-page experience using React Hook Form and Stripe Elements, increasing conversion rate from 62% to 79%\n"
                "- Migrated global state from Redux (142 actions, 38 reducers) to React Query + Zustand, eliminating 4,200 lines of boilerplate and reducing state-related bugs by 60%"
            )},
        ],
        "skills": [{"text": "TypeScript, React, Next.js, Redux, Storybook, Stripe"}],
    },
    "faang_fullstack_1": {
        "vertical": "SWE",
        "experience": [
            {"text": (
                "Full-Stack Engineer -- 2019-Present\n"
                "- Built the multi-tenant workspace feature end-to-end (React frontend with role-based UI, Node.js/Express API with row-level security in PostgreSQL), onboarding 120 enterprise teams\n"
                "- Implemented full-text search across 4.2M product listings using Elasticsearch, with a React autocomplete UI featuring debounced queries and highlighted results\n"
                "- Built a self-service reporting system with a drag-and-drop query builder (React DnD) backed by a SQL generation engine and scheduled PDF export, used by 200+ account managers\n"
                "- Rebuilt the user onboarding flow (interactive React wizard, backend event tracking via Segment, automated drip emails via SendGrid), increasing 7-day activation rate from 23% to 41%"
            )},
        ],
        "skills": [{"text": "React, Node.js, PostgreSQL, Elasticsearch, Segment"}],
    },
    "faang_devops_1": {
        "vertical": "SWE",
        "experience": [
            {"text": (
                "Site Reliability Engineer -- 2020-Present\n"
                "- Redesigned CI/CD from Jenkins to GitHub Actions across 32 repositories, reducing average build time from 24 minutes to 7 minutes and enabling 85 production deployments/week (up from 12)\n"
                "- Migrated 140+ AWS resources from manual console management to Terraform modules with remote state and automated plan/apply via Atlantis, eliminating configuration drift\n"
                "- Built an observability stack with Prometheus, Grafana, and PagerDuty (120 custom metrics, 45 alert rules), reducing mean time to detection from 38 minutes to under 3 minutes\n"
                "- Architected a multi-account AWS organization (12 accounts, 3 environments) with cross-account IAM roles and centralized CloudTrail logging, passing SOC 2 Type II audit with zero critical findings"
            )},
        ],
        "skills": [{"text": "Terraform, AWS, Kubernetes, Prometheus, Grafana"}],
    },
    "faang_newgrad_1": {
        "vertical": "SWE",
        "experience": [
            {"text": (
                "Software Engineering Intern -- Summer 2025\n"
                "- Trained a BERT-based text classifier on 50K labeled support tickets, achieving 91% F1-score, deployed as a FastAPI microservice that auto-routes 2K tickets/day"
            )},
        ],
        "projects": [
            {"text": "Implemented a Raft consensus protocol in Rust with leader election, log replication, and snapshotting, passed 200+ Jepsen-style fault injection tests and benchmarked at 12K writes/sec."},
            {"text": "Won 1st place at a 800-participant hackathon, built a browser extension using Chrome APIs and an LLM API that summarizes Terms of Service pages into plain-language risk scores."},
        ],
        "skills": [{"text": "Rust, Python, FastAPI, Distributed Systems"}],
        "education": [{"text": "B.S. Computer Science -- 2026"}],
    },
    "faang_backend_2": {
        "vertical": "SWE",
        "experience": [
            {"text": (
                "Backend Engineer, Payments -- 2021-Present\n"
                "- Integrated Stripe Connect for marketplace payouts across 3 currencies, processing $4.2M in monthly transaction volume with a 99.98% success rate\n"
                "- Re-architected the notification service from synchronous HTTP to an async queue-based system (SQS + Lambda), enabling horizontal scaling from 500 to 25K notifications/minute\n"
                "- Reduced backend technical debt by refactoring 18K lines of legacy PHP into typed TypeScript modules, increasing unit test coverage from 12% to 78%"
            )},
        ],
        "skills": [{"text": "TypeScript, AWS Lambda, SQS, Stripe API"}],
    },
    "faang_frontend_2": {
        "vertical": "SWE",
        "experience": [
            {"text": (
                "Frontend Engineer, Accessibility -- 2022-Present\n"
                "- Audited and remediated 340 WCAG 2.1 AA violations across 28 pages using axe-core and manual screen-reader testing, achieving full compliance\n"
                "- Built a real-time collaborative whiteboard using WebRTC data channels and Canvas API, supporting up to 20 concurrent users with <50ms drawing latency\n"
                "- Shipped a cross-platform mobile app in React Native serving 85K MAU, implementing offline-first sync with WatermelonDB and achieving a 4.7-star App Store rating"
            )},
        ],
        "skills": [{"text": "React Native, WebRTC, Canvas API, axe-core"}],
    },
    "hft_quant_researcher_1": {
        "vertical": "HFT/Quant",
        "experience": [
            {"text": (
                "Quantitative Researcher -- 2021-Present\n"
                "- Built a factor model combining momentum and value signals across 2,000 US equities, improving portfolio Sharpe ratio from 0.9 to 1.4 on out-of-sample data\n"
                "- Improved daily strategy information coefficient from 0.04 to 0.12, contributing $2.1M annualized gross alpha\n"
                "- Backtested 40+ candidate signals across a 10-year equity universe using a custom Python/C++ research framework, promoting 6 to live production"
            )},
        ],
        "skills": [{"text": "Python, C++, NumPy, Statistical Modeling, Factor Models"}],
        "education": [{"text": "M.S. Financial Engineering -- 2021"}],
    },
    "hft_quant_dev_1": {
        "vertical": "HFT/Quant",
        "experience": [
            {"text": (
                "Quantitative Developer, Market Making -- 2020-Present\n"
                "- Reduced order-to-execution latency by 60% to 120 microseconds through kernel bypass networking and lock-free data structures, enabling competitive market-maker quoting\n"
                "- Rewrote the tick-to-trade pipeline in C++ with a custom memory allocator, cutting p99 tail latency from 800us to 140us under peak load\n"
                "- Built a real-time risk monitoring system processing 400K market events/second, flagging limit breaches within 2ms"
            )},
        ],
        "skills": [{"text": "C++, Linux kernel bypass, FPGA basics, Low-latency systems"}],
    },
    "hft_quant_strat_1": {
        "vertical": "HFT/Quant",
        "experience": [
            {"text": (
                "Quantitative Trader -- 2019-Present\n"
                "- Designed and ran a statistical arbitrage strategy across 150 correlated equity pairs, generating $3.4M in annual P&L with a 1.8 Sharpe ratio\n"
                "- Redesigned position-sizing logic using a Kelly-criterion variant, reducing max drawdown from 18% to 9% without lowering annualized return\n"
                "- Automated end-of-day PnL attribution reporting across 12 strategies, cutting manual reconciliation time from 3 hours to 15 minutes daily"
            )},
        ],
        "skills": [{"text": "Python, R, Statistical Arbitrage, Risk Management"}],
    },
    "hft_quant_researcher_2": {
        "vertical": "HFT/Quant",
        "experience": [
            {"text": (
                "Quantitative Research Associate -- 2022-Present\n"
                "- Developed a machine-learning-based order flow imbalance predictor, improving fill rate on passive orders by 22% in live A/B testing\n"
                "- Built a market impact model calibrated on 3 years of tick data across 500 tickers, reducing average slippage on large orders by 14 basis points"
            )},
        ],
        "skills": [{"text": "Python, scikit-learn, Market Microstructure"}],
    },
    "ib_ma_analyst_1": {
        "vertical": "IB",
        "experience": [
            {"text": (
                "Investment Banking Analyst, M&A -- 2022-Present\n"
                "- Executed buy-side M&A advisory for a $1.2B healthcare acquisition, leading financial modeling, due diligence coordination, and management presentation materials\n"
                "- Built DCF, LBO, and comparable company analyses for 12 live deals ranging from $80M to $1.5B in transaction value\n"
                "- Coordinated due diligence workstreams across legal, accounting, and operations teams for a $600M cross-border acquisition, closing 3 weeks ahead of schedule"
            )},
        ],
        "skills": [{"text": "Excel, DCF Modeling, LBO Modeling, Capital IQ"}],
    },
    "ib_sellside_1": {
        "vertical": "IB",
        "experience": [
            {"text": (
                "Investment Banking Analyst, Industrials -- 2021-Present\n"
                "- Developed slides for a $250M sell-side M&A pitch deck by analyzing industry comparables and precedent transactions across 30+ target companies\n"
                "- Built and maintained a comps universe of 45 public industrials companies, refreshed weekly for use across 8 active client engagements\n"
                "- Prepared management presentation materials for a successful $180M divestiture, presented directly to the client's board"
            )},
        ],
        "skills": [{"text": "Comparable Company Analysis, PowerPoint, Bloomberg"}],
    },
    "ib_lbo_1": {
        "vertical": "IB",
        "experience": [
            {"text": (
                "Investment Banking Analyst, Leveraged Finance -- 2020-Present\n"
                "- Engineered a $150M acquisition deal for a private equity client using DCF and LBO models, supporting a valuation 35% above the initial bid, deal closed successfully\n"
                "- Structured a $400M leveraged buyout financing package across senior debt, mezzanine, and equity tranches\n"
                "- Ran sensitivity analysis across 6 leverage scenarios for a $220M add-on acquisition, directly informing the client's final bid strategy"
            )},
        ],
        "skills": [{"text": "LBO Modeling, Debt Structuring, Excel VBA"}],
    },
    "ib_generalist_1": {
        "vertical": "IB",
        "experience": [
            {"text": (
                "Investment Banking Summer Analyst -- Summer 2025\n"
                "- Supported execution of a $90M sell-side transaction, building the management presentation and coordinating a 25-company buyer outreach process\n"
                "- Built a merger consequences model for a $340M stock-for-stock merger, analyzing pro forma EPS accretion/dilution across 4 financing scenarios"
            )},
        ],
        "skills": [{"text": "Financial Modeling, Merger Consequences Analysis"}],
        "education": [{"text": "B.S. Finance -- 2026"}],
    },
}

MID_TIER = {
    "mid_swe_support_1": {
        "vertical": "SWE",
        "experience": [
            {"text": (
                "IT Support Engineer -- 2020-2023\n"
                "- Provided technical support to end users for hardware and software issues\n"
                "- Resolved around 15 tickets per day on average using the internal ticketing system\n"
                "- Assisted in setting up new employee laptops and configuring VPN access\n"
                "- Coordinated with the networking team to troubleshoot connectivity issues"
            )},
            {"text": (
                "Junior Developer, Local Startup -- 2023-Present\n"
                "- Fixed bugs in the company's internal CRM tool\n"
                "- Wrote unit tests for a couple of modules, improving test coverage somewhat\n"
                "- Participated in daily standups and sprint planning"
            )},
        ],
        "skills": [{"text": "Java, SQL, Git, JIRA, basic Python"}],
        "education": [{"text": "B.Tech Information Technology -- 2020"}],
    },
    "mid_swe_2": {
        "vertical": "SWE",
        "experience": [
            {"text": (
                "Software Developer -- 2021-Present\n"
                "- Developed and maintained internal web applications for the operations team\n"
                "- Worked with senior engineers to fix production bugs, usually 3-5 per sprint\n"
                "- Wrote documentation for a couple of internal APIs\n"
                "- Attended code reviews and gave feedback on some pull requests"
            )},
        ],
        "skills": [{"text": "JavaScript, Node.js, MySQL"}],
    },
    "mid_finance_analyst_1": {
        "vertical": "IB",
        "experience": [
            {"text": (
                "Financial Analyst, Corporate FP&A -- 2021-Present\n"
                "- Prepared monthly financial reports for the finance leadership team\n"
                "- Helped build the annual budget model with input from department heads\n"
                "- Analyzed variances between actual and budgeted spend across a few departments\n"
                "- Supported the finance team during the year-end audit process"
            )},
        ],
        "skills": [{"text": "Excel, financial reporting, budgeting"}],
    },
    "mid_quant_1": {
        "vertical": "HFT/Quant",
        "experience": [
            {"text": (
                "Data Analyst, Trading Support -- 2022-Present\n"
                "- Built some Python scripts to help clean and process trading data\n"
                "- Assisted the quant team with backtesting a couple of strategy ideas\n"
                "- Created dashboards to track daily PnL for the desk\n"
                "- Helped troubleshoot data quality issues in the market data pipeline"
            )},
        ],
        "skills": [{"text": "Python, SQL, Excel"}],
    },
    "mid_swe_3": {
        "vertical": "SWE",
        "experience": [
            {"text": (
                "Associate Software Engineer -- 2022-Present\n"
                "- Implemented a few new features for the mobile app based on product requirements\n"
                "- Fixed several customer-reported bugs each sprint\n"
                "- Helped migrate part of the codebase to a newer framework version\n"
                "- Collaborated with the QA team to reproduce and resolve reported issues"
            )},
        ],
        "skills": [{"text": "Swift, Kotlin, REST APIs"}],
    },
}

BAD_TIER = {
    "bad_swe_1": {
        "vertical": "SWE",
        "experience": [
            {"text": (
                "Senior Manager of Being Busy -- 2021-Present\n"
                "- Responsible for managing team projects and deadlines\n"
                "- Helped with various cross-functional initiatives\n"
                "- Worked on improving processes and workflows\n"
                "- Was involved in strategic planning discussions"
            )},
            {"text": (
                "Assistant to the Regional Buzzwords -- 2019-2021\n"
                "- Responsible for day-to-day operational tasks\n"
                "- Helped support the team with various duties"
            )},
        ],
        "skills": [{"text": "Microsoft Word (Advanced), Team Player, Self Starter, Results-Driven, Synergy"}],
    },
    "bad_swe_2": {
        "vertical": "SWE",
        "experience": [
            {"text": (
                "Software Engineer -- 2020-Present\n"
                "- Developed admin dashboard\n"
                "- Managed CI/CD pipelines\n"
                "- Implemented infrastructure as code\n"
                "- Worked on code quality improvements"
            )},
        ],
        "skills": [{"text": "Programming, Computers, Problem Solving"}],
    },
    "bad_swe_3": {
        "vertical": "SWE",
        "experience": [
            {"text": (
                "IT Professional -- 2021-Present\n"
                "- Responsible for various IT tasks\n"
                "- Helped with computer issues\n"
                "- Worked on projects as assigned\n"
                "- Participated in meetings"
            )},
        ],
        "skills": [{"text": "Hard Working, Fast Learner, Detail Oriented"}],
    },
    "bad_finance_1": {
        "vertical": "IB",
        "experience": [
            {"text": (
                "Finance Professional -- 2022-Present\n"
                "- Responsible for financial tasks and reporting\n"
                "- Helped with various banking activities\n"
                "- Worked on deals as needed\n"
                "- Assisted senior team members"
            )},
        ],
        "skills": [{"text": "Excel, PowerPoint, Communication"}],
    },
    "bad_quant_1": {
        "vertical": "HFT/Quant",
        "experience": [
            {"text": (
                "Quant Professional -- 2021-Present\n"
                "- Responsible for quantitative work\n"
                "- Helped the trading team with analysis\n"
                "- Worked on models as assigned\n"
                "- Participated in strategy discussions"
            )},
        ],
        "skills": [{"text": "Python, Math, Statistics"}],
    },
}
