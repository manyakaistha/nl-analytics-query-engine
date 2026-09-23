**Build an Intelligent Analytics Query Engine**

---

**🎯 Problem Statement**

You are given a dataset and a set of natural language queries.

Build a system that:

Converts natural language into executable analytical queries and returns correct results.

---

**📦 Dataset**

You will receive:

/dataset

&nbsp;&nbsp;├── sales\_data.csv

&nbsp;&nbsp;├── targets.csv

&nbsp;&nbsp;├── data\_dictionary.json

&nbsp;&nbsp;├── nl\_queries.json

&nbsp;

---

**⚙️ Requirements**

Your system must:

**1\. Understand Natural Language**

* Interpret user queries&nbsp;  
* Map business terms to data fields&nbsp;

---

**2\. Generate Executable Logic**

* Convert queries into:&nbsp;  
  * SQL / Pandas / any executable form&nbsp;  
* Must support:&nbsp;  
  * Aggregations&nbsp;  
  * Grouping&nbsp;  
  * Filtering&nbsp;  
  * Ranking&nbsp;  
  * Comparisons&nbsp;

---

**3\. Execute and Return Results**

* Run the generated logic on the dataset&nbsp;  
* Return correct outputs&nbsp;

---

**4\. Handle Complex Queries**

Your system should handle cases like:

* Top N within groups&nbsp;  
* Contribution percentages&nbsp;  
* Nested logic&nbsp;  
* Comparisons with targets&nbsp;  
* Time-based queries&nbsp;

---

**5\. Use GenAI**

You must use GenAI meaningfully.

---

**6\. Confidence Score**

For every query, return a confidence score:

0 → unreliable

1 → highly confident

---

**7\. Explanation**

For each output, include:

* What the system understood&nbsp;  
* How it generated the result&nbsp;

---

**8\. Feedback Loop**

Use feedback\_log.csv (if provided) to improve results.

---

**📤 Expected Output Format**

{

&nbsp;&nbsp;"query": "...",

&nbsp;&nbsp;"generated\_logic": "...",

&nbsp;&nbsp;"result": "...",

&nbsp;&nbsp;"confidence\_score": 0.0,

&nbsp;&nbsp;"explanation": "..."

}

---

**📌 Constraints**

* No hardcoding answers&nbsp;  
* Must work for unseen queries&nbsp;  
* System design matters more than UI&nbsp;

---

**📦 Deliverables**

1. Code (GitHub or zip)&nbsp;  
2. README explaining:&nbsp;  
   * Approach&nbsp;  
   * Architecture&nbsp;  
   * Tradeoffs&nbsp;  
3. Sample outputs&nbsp;  
4. (Optional) Improvements if given more time&nbsp;

---

**⏱️ Time Expectation**

4–8 hours

---

**🧪 Evaluation Criteria**

* Correctness&nbsp;  
* Use of GenAI&nbsp;  
* System design&nbsp;  
* Handling of edge cases&nbsp;  
* Clarity of thinking&nbsp;

---

**❗ Important**

* There is no single correct approach&nbsp;  
* Focus on building a robust system&nbsp;  
* Keep assumptions minimal

&nbsp;