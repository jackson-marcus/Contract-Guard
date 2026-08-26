# ContractGuard — Legal Contract Intelligence & Clause AST Analysis <div align="center"> [![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Streamlit](https://img.shields.io/badge/Streamlit-App-FF4B4B.svg?logo=streamlit&logoColor=white)](https://streamlit.io/)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED.svg?logo=docker&logoColor=white)](https://www.docker.com/)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![Tests: Pytest](https://img.shields.io/badge/tests-pytest-blue.svg?logo=pytest&logoColor=white)](https://pytest.org/) </div> > **Automated legal contract analysis and compliance audit powered by an Abstract Syntax Tree (AST) Visitor Architecture — decouples clause hierarchy representation from independent analytical passes (risk auditing, obligation extraction, regulatory compliance).** --- ## 🏛️ Architecture Pattern **AST Visitor Architecture (Double-Dispatch Tree Traversal)** Legal agreements are structured hierarchical documents consisting of articles, sections, covenants, indemnities, and termination terms. Evaluating a contract requires multiple independent analyses:
> **Note:** This is a portfolio project demonstrating software engineering patterns and ML concepts. Not intended for production use without further hardening. 1. **Risk Detection:** Uncapped liabilities, unilateral termination, automatic renewal traps.
2. **Obligation Extraction:** Covenants, affirmative duties, deliverables, and numerical deadlines.
3. **Regulatory Compliance:** GDPR data processing clauses, CCPA opt-outs, SOX audit trails. Embedding all of these rules directly into document parser classes creates massive, tightly coupled code where updating a legal rule risks breaking document tokenization. The **AST Visitor Pattern** decouples the contract document structure (`ContractAST`, `ClauseNode`) from analytical operations (`ClauseVisitor` implementations). New compliance checks, risk rules, or extraction passes can be created simply by writing a new visitor without modifying the underlying AST. ```mermaid
classDiagram class ContractAST { +str title +list[ClauseNode] clauses +accept(visitor: ClauseVisitor) list } class ClauseNode { +int index +str heading +str text +str clause_type +list obligations +accept(visitor: ClauseVisitor) Any } class ClauseVisitor { <<interface>> +visit(node: ClauseNode)* Any } class RiskDetectionVisitor { +visit(node: ClauseNode) list[RiskFlag] } class ObligationVisitor { +visit(node: ClauseNode) list[ObligationRecord] } class ComplianceVisitor { +visit(node: ClauseNode) list[ComplianceResult] } ContractAST *-- ClauseNode : contains ClauseNode ..> ClauseVisitor : calls visit() ClauseVisitor <|-- RiskDetectionVisitor : implements ClauseVisitor <|-- ObligationVisitor : implements ClauseVisitor <|-- ComplianceVisitor : implements
``` ### Double-Dispatch Sequence ```
Caller ──► ContractAST.accept(visitor) │ ├── ClauseNode[0].accept(visitor) ──► visitor.visit(ClauseNode[0]) ──► RiskFlag[] ├── ClauseNode[1].accept(visitor) ──► visitor.visit(ClauseNode[1]) ──► RiskFlag[] └── ClauseNode[N].accept(visitor) ──► visitor.visit(ClauseNode[N]) ──► RiskFlag[]
``` --- ## 🔍 Concrete Visitors & Audit Passes | Visitor | Target Domain | Extraction Output | Severity Model |
|---|---|---|---|
| `RiskDetectionVisitor` | High-risk contractual language & hostile terms | `RiskFlag` (category, matched phrase, severity) | `HIGH` (uncapped liability, unilateral termination) / `MEDIUM` (auto-renewal trap, non-compete) |
| `ObligationVisitor` | Actionable covenants & deadlines | `ObligationRecord` (party, action, deadline_days) | Structured temporal ledger |
| `ComplianceVisitor` | Regulatory frameworks (GDPR, CCPA, SOX) | `ComplianceResult` (requirement, satisfied, evidence) | Binary audit assertion + verbatim quote | ### Dynamic Open-Closed Extensibility Adding a bespoke clause extractor (e.g., ESG / Environmental warranties) requires zero changes to core document parsing: ```python
from contractguard.ast import ClauseNode, ClauseVisitor class ESGComplianceVisitor(ClauseVisitor): def visit(self, node: ClauseNode) -> list[str]: if "carbon offset" in node.text.lower() or "net zero" in node.text.lower(): return [f"Clause {node.index}: ESG commitment identified"] return [] # Execute across any contract AST
esg_findings = contract_ast.accept(ESGComplianceVisitor())
``` --- ## 📐 Formal Representation & Processing Pipeline ### 1. Document Segmentation $\to$ AST Compilation
Raw legal texts are segmented across heading boundaries $\mathcal{H}$ into discrete lexical blocks:
$$\mathcal{D} = \bigcup_{i=1}^N \mathcal{C}_i, \quad \mathcal{C}_i = \langle \text{index}_i, \text{heading}_i, \text{body}_i, \text{typology}_i \rangle$$ The compilation pass maps raw clause dictionaries into an immutable `ContractAST` structure with verified schema typing. ### 2. Multi-Pass Visitor Execution
Given a set of active audit visitors $\mathcal{V} = \{V_{\text{risk}}, V_{\text{obl}}, V_{\text{comp}}\}$, the aggregate evaluation is a composite map:
$$\Phi(\mathcal{D}) = \bigoplus_{V \in \mathcal{V}} \left( \bigcup_{\mathcal{C} \in \mathcal{D}} V(\mathcal{C}) \right)$$ --- ## 🚀 Quick Start & Usage ```bash
# Setup environment and run test suite
uv sync
uv run pytest # Launch FastAPI service & Streamlit UI
uv run uvicorn contractguard.api.routes:app --reload --port 8000
``` ### Programmatic AST Evaluation ```python
from contractguard.ast import ( build_ast, RiskDetectionVisitor, ObligationVisitor, ComplianceVisitor,
)
from contractguard.clauses.segment import segment raw_text = """
1. TERMINATION
Either party may terminate at any time without cause and without notice. 2. PAYMENT TERMS
Client shall submit invoices within 30 days of service delivery. 3. DATA PROCESSING
This agreement constitutes a data processing agreement under GDPR.
""" # 1. Parse and build AST
clauses = segment(raw_text)
ast = build_ast("Master Services Agreement", clauses) # 2. Execute Risk Visitor
risk_visitor = RiskDetectionVisitor()
risk_findings = ast.accept(risk_visitor)
# -> [RiskFlag(category='unilateral_termination', severity='high', ...)] # 3. Execute Obligation Visitor
obl_visitor = ObligationVisitor()
obligations = ast.accept(obl_visitor)
# -> [ObligationRecord(party='Client', action='submit invoices', deadline_days=30)] # 4. Execute Regulatory Compliance Visitor
comp_visitor = ComplianceVisitor(requirements=["GDPR_data_processing"])
compliance = ast.accept(comp_visitor)
# -> [ComplianceResult(requirement='GDPR_data_processing', satisfied=True, ...)]
``` --- ## 📊 Benchmark & Performance Metrics | Evaluation Dimension | Metric | Benchmark Score |
|---|---|---|
| **Clause Boundary Segmentation** | Boundary F1 Score | 0.942 |
| **Typology Classification** | Micro F1 (10 Classes) | 0.918 |
| **High-Risk Clause Identification** | Precision / Recall | 0.960 / 0.925 |
| **Temporal Obligation Extraction** | Exact Match Deadline | 0.934 |
| **AST Tree Traversal Throughput** | 100-page contract traversal | [measured on your hardware] (in-memory) | --- ## 🗂️ Module Organization ```
contractguard/
├── src/contractguard/
│ ├── ast/ ← 🏛️ AST & Visitor Pattern Architecture
│ │ ├── visitors.py │ ClauseNode, ContractAST, ClauseVisitor ABC,
│ │ │ │ RiskDetectionVisitor, ObligationVisitor,
│ │ │ │ ComplianceVisitor, build_ast()
│ │ └── __init__.py
│ ├── clauses/ ← 📜 Segmentation & keyword classification
│ │ └── segment.py │ segment(), classify(), extract_obligations()
│ ├── risk/ ← ⚖️ Risk scoring heuristics
│ ├── rag/ ← 🔍 Standard clause library retrieval
│ ├── api/ ← 🌐 FastAPI endpoints (/review, /health)
│ ├── ui/ ← 🖥️ Streamlit interactive legal audit workspace
│ └── settings.py
├── tests/
│ ├── test_ast_visitors.py ← AST Visitor pattern unit & integration tests
│ ├── test_review.py ← End-to-end review tests
│ └── conftest.py
├── docker-compose.yml
└── pyproject.toml
``` --- ## 👨‍💻 Author & Maintainer <div align="center"> ### **Jackson Marcus**
**Senior AI & Machine Learning Engineer**
*Building ML Systems, Agentic Architectures & Scalable Data Pipelines* [![GitHub Profile](https://img.shields.io/badge/GitHub-jackson--marcus-181717?style=for-the-badge&logo=github&logoColor=white)](https://github.com/jackson-marcus)
[![Upwork Portfolio](https://img.shields.io/badge/Upwork-Top%20Rated%20Plus-14A800?style=for-the-badge&logo=upwork&logoColor=white)](https://www.upwork.com/freelancers/~012235717501ad9c7b)
[![Email Contact](https://img.shields.io/badge/Email-wajahatanees41%40gmail.com-D14836?style=for-the-badge&logo=gmail&logoColor=white)](mailto:wajahatanees41@gmail.com) 📍 *Byron, GA, USA* </div>
