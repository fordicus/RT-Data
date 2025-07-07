### RULESET.md — Unified Guidelines (2025-07-07)

> **Purpose**  
> This file serves as a unified and authoritative guideline for code, documents,  
> and supporting assets across the project.  
> It defines both human and AI-facing conventions, ensuring clarity, consistency,  
> and maintainability from development to delivery.

> ⚠️ AI developers (e.g., ChatGPT, Copilot) are expected to read and follow  
> this RULESET explicitly. This document is your shared contract with the AI.

---

## 1  Global Principles   🌐

| ID   | Rule                                                                                                                      |
|------|---------------------------------------------------------------------------------------------------------------------------|
| G-1  | **Readability first** — Ensure clear structure with ≤ 80 characters per line, including comments and docstrings. Break long lines into multiple shorter ones for better readability. |
| G-2  | **Precise English Comments only** — All comments must be written in clear, precise English. No other language allowed.    |
|      | Comments must be critical, succinct, and technically informative. Explain subtle logic or assumptions inline where needed. |
| G-3  | **Use tabs, not spaces** — Applies to code, docstrings, Markdown, and LaTeX.                                              |
| G-4  | **Keep history traceable** — Never alter program logic during reformatting. Use comments and commits to explain intent.  |
| G-5  | **Output in chat only** — All assistant replies must appear in the chat window unless explicitly asked otherwise.         |
| G-6  | **Latest upload wins** — Always treat the most recently uploaded file as authoritative.                                   |
| G-7  | **DO NOT DELETE** — Do not remove any comment or code block marked with this phrase unless it's demonstrably obsolete.    |
| G-8  | **No Canvas (ChatGPT only)** — Scripts, outputs, and updates must be shown in this chat session, not in canvas panels.    |
| G-9  | **Strict adherence to rules** — All AI agents must strictly follow the rules outlined in this document when collaborating on code-related tasks. |

---

## 2  Generic Scripting & Programming   🛠️

1. **Human-friendly layout**  
   → Use short logical blocks, insert blank lines around comments, and structure sections clearly.

2. **Cross-language fallback**  
   → In the absence of a language-specific rule, follow Python-style conventions (e.g., docstring structure).

3. **No long one-liners**  
   → Break up complex logic for clarity. Align operators and argument lists when beneficial.

4. **Comment scope**  
   → Every non-trivial loop, branch, or algorithm must have a clear comment above it.  
   Do not comment the obvious. Favor meaningful guidance.

5. **Multiline comments**  
   → Always use the multiline comment syntax supported by the language  
   (e.g., `/* ... */` in JS/TS, `"""..."""` in Python).  
   Avoid repeating `//` or `#` across lines.

6. **Precise + Inclusive Explanation**
   → Comments and docstrings should be crafted to aid understanding for  
   technically skilled contributors from **different backgrounds**.

   🧠 Example:  
   A mathematician working on reinforcement learning and order-book modeling  
   might not be fluent in generic web frameworks (e.g., FastAPI, Vite).  
   A well-placed docstring like:

       "FastAPI is a stateless web API server that helps you construct
        REST endpoints in Python quickly and safely."

   ...makes the project more accessible, especially in AI-augmented workflows  
   where explanations are dynamically reused by the assistant.

   📌 Sub-discipline-specific jargons often create communication inefficiency.  
   Favor clear definitions and structured analogies over insider shorthand.

   ✅ Aim for:
   - precise, one-line definitions for libraries or concepts
   - conceptual analogies if appropriate (e.g., "FastAPI ~ stateless mapping")
   - minimal but useful scaffolding for context

   ❌ Avoid:
   - assuming domain familiarity (e.g., frontend routing, Docker internals)
   - bloated general-purpose introductions

   ✨ Think of each comment as onboarding your future self — or your AI pair.


---

## 2A  Global Docstring for Main Entry Points   📘

This rule governs files like `main.ts`, `main.py`, or other top-level orchestration scripts.

These scripts often coordinate multiple components (e.g., frontend + backend),  
so they should begin with a structured multiline docstring that provides the high-level context  
for both human readers and AI assistants.

🟦 Target Format:

```ts
/** ============================================================================
 * Project Overview:
 * Frontend Technology:
 * Backend Integration:
 * How to Run (Dev Only):
 * Limitation:
 * TODO (DO NOT DELETE):
 * ============================================================================
 */
````

🟡 Guidelines:

* This format serves as a **long-form metadata block**, meant to evolve across the project's lifecycle.
* It is not required at project start but should be fully populated by the delivery or review stage.
* You may extend or omit sections as appropriate, but follow the structural intent.
* Example API endpoints (GET/curl), runtime versions, and key filenames are encouraged.

🧠 Note:
This docstring structure is designed with AI-assisted comprehension in mind.
Think of it as a persistent onboarding layer for both your teammates and your future self.

---

## 3  Python — Module Docstrings & Inline Comments   🐍

| Section          | Rule                                                                                                              |
| ---------------- | ----------------------------------------------------------------------------------------------------------------- |
| Header format    | Use raw triple-quoted string `r""" ... """`, enclosed with **exactly 80 dots** on top and bottom.                 |
| Mandatory blocks | Must contain (in order): `How to Use`, `Dependency`, `Functionality`, `IO Structure`. Each block title is capped. |
| Alignment        | Use tabs for all indentation. Maintain internal layout grid-style.                                                |
| Emphasis         | Use `NOTE:` or `IMPORTANT:` — do not use Markdown formatting.                                                     |
| Inline comments  | Write concise English (≤ 80 chars), tab-indented, placed above multi-line logic with a blank line before/after.   |
| Safe edits       | You may reformat or comment, but must not alter logic or behavior.                                                |

---

## 4  Markdown Documentation   📄

1. Use `#`, `##`, `###` for heading levels. Do not prefix headings with numbers.
2. Emoji prefixes (`📐`, `🔍`, `🧩`) are allowed if they improve skimming.
3. Ensure headings follow a logical order for TOC generation.

---

## 5  LaTeX Tables   📊

| Rule | Description                                                                                                                                                                                     |
| ---- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| L-1  | **No vertical lines** — use spacing and `booktabs` instead.                                                                                                                                         |
| L-2  | **Full width** — all tables should span `\textwidth`.                                                                                                                                               |
| L-3  | Use `tabularx` and `booktabs` to manage column spacing and table layout.                                                                                                                        |
| L-4  | For controlling text alignment inside table cells (e.g., full justification), use `ragged2e` and define an appropriate column type (e.g., `J{}` with `\justifying`). Example usage shown below. |
| L-5  | **Caption on top**, followed by `\vspace{0.5em}` before the table body begins. Use Title Case for table captions: capitalize the first letter of major words.                                       |
| L-6  | Only use `\toprule`, `\midrule`, and `\bottomrule` for horizontal lines.                                                                                                                        |
| L-7  | Use `@{}` in column templates to remove outer padding (e.g., `@{} l X @{}`).                                                                                                                    |


---

### ✅ Example for Full-Justified Column (J{}) Template

```latex
%---------------------------------------------------------------
% table
%...............................................................
\usepackage{tabularx, booktabs, ragged2e}
\newcolumntype{L}[1]{>{\raggedright\arraybackslash}p{#1}}
\newcolumntype{J}[1]{>{\noindent\justifying\arraybackslash}p{#1}}
%...............................................................
% tabularx spans \textwidth, and
% J{6.4cm}/J{6.4cm} ensures full-justified columns for long text blocks
%...............................................................
\begin{table}[h]
\centering
\begin{tabularx}{\textwidth}{@{}lJ{6.4cm}J{6.4cm}@{}}
\toprule
\textbf{Approach} & \textbf{Advantage} & \textbf{Limitation} \\
\midrule

Classification & 
Reduces the dimensionality of the prediction output.  
Offers high parameter and sample efficiency;  
may achieve a relatively better accuracy with fewer parameters even under limited data.

& 
Temporal sparsity occurs as intermediate price actions not included in the predefined $\tau$ set are lost.  
Even with accurate predictions, fine-grained signals for entry/exit timing may be lacking for trading decisions.

\\

Vector Generation & 
Provides a sequence of returns at uniformly spaced future time points.  
Useful not only for trading decisions, but also for risk assessment, position sizing,  
and trajectory-based strategy design.

& 
As the prediction horizon length increases, sample efficiency degrades and solvability requires more model parameters and larger datasets.  
This creates a trade-off with the advantages of the classification approach.

\\

\bottomrule
\end{tabularx}
\caption{Advantages and limitations of classification and vector generation approaches}
\end{table}
```

---

## 6  File-Specific Precedence   📁

> *Always honor the most recently uploaded file of any given name.*
> Identical filenames do not imply identical content.
> See G-6.

---