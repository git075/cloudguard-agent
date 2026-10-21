# 🎨 UI/UX Design System & Dashboard Blueprint
## Project: CloudGuard FinOps Engine

---

## 1. Visual Aesthetics & Design System

To ensure a high-converting, modern, wowed experience, CloudGuard utilizes a **sleek dark-mode glassmorphism** theme built with Vanilla CSS or TailwindCSS + Framer Motion.

### 1.1 Color Palette Tokens

```css
:root {
  /* Dark Canvas Base */
  --bg-dark: #090D16;
  --bg-card: rgba(18, 24, 38, 0.7);
  --bg-card-border: rgba(255, 255, 255, 0.08);

  /* Primary Brand Accents */
  --emerald-primary: #10B981;  /* High Savings / Approved State */
  --emerald-glow: rgba(16, 185, 129, 0.25);
  
  --indigo-accent: #6366F1;   /* Primary Buttons / Active Tabs */
  --indigo-glow: rgba(99, 102, 241, 0.3);

  /* Alerts & Safety Tokens */
  --amber-warn: #F59E0B;      /* Invariant Warn Mode */
  --rose-block: #EF4444;      /* Invariant Block / Drift Anomaly */

  /* Typography */
  --font-heading: 'Outfit', sans-serif;
  --font-body: 'Inter', sans-serif;
  --font-code: 'JetBrains Mono', monospace;
}
```

---

## 2. Page Hierarchy & Layout Blueprints

### Page 1: Customer Executive Dashboard (`/dashboard`)

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ ☁️ CloudGuard FinOps                AWS: Production-Account-101   [ ⚡ Scan Account ] │
├────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                        │
│  ┌───────────────────────┐  ┌───────────────────────┐  ┌────────────────────────────┐  │
│  │ Annualized Savings    │  │ Active GitHub PRs     │  │ StateGuard Protection Rate │  │
│  │   $24,500 / yr        │  │     6 Open PRs        │  │    100% Zero Outages       │  │
│  └───────────────────────┘  └───────────────────────┘  └────────────────────────────┘  │
│                                                                                        │
│  ┌──────────────────────────────────────────────────────────────────────────────────┐  │
│  │ ⚡ Active Cost Remediation Pull Requests                                         │  │
│  ├──────────────────────────────────────────────────────────────────────────────────┤  │
│  │ PR #42 | db.r5.2xlarge ➔ db.r6g.xlarge  | Save $950/mo  | [ View PR ] [ Merge ]  │  │
│  │ PR #45 | Unattached EBS Volume (500GB)  | Save $120/mo  | [ View PR ] [ Merge ]  │  │
│  │ PR #48 | ec2.m5.xlarge ➔ ec2.t4g.large  | Save $180/mo  | [ View PR ] [ Merge ]  │  │
│  └──────────────────────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Key UI Components

### 3.1 The "StateGuard Safety Proof Badge" Component
Every Pull Request card displays an interactive StateGuard proof badge:

```tsx
<div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-emerald-950/40 border border-emerald-500/30">
  <ShieldCheckIcon className="w-4 h-4 text-emerald-400 animate-pulse" />
  <span className="text-xs font-mono text-emerald-300">
    StateGuard Invariants Verified (CPU Max: 42% &lt; 80% Threshold)
  </span>
</div>
```

### 3.2 The GitHub PR Markdown Widget
When CloudGuard opens a Pull Request, it embeds a rich Markdown comment into GitHub:

```markdown
## ⚡ CloudGuard Cost Optimization Suggestion

| Metric | Before | After (Proposed) | Net Change |
| :--- | :--- | :--- | :--- |
| **Instance Type** | `db.r5.2xlarge` | `db.r6g.xlarge` | Graviton ARM Migration |
| **vCPU / Memory** | 8 vCPU / 64 GB | 4 vCPU / 32 GB | Right-Sized to Peak Load |
| **Monthly Cost** | **$1,400.00** | **$450.00** | **-$950.00 / month (68%)** |

### 🛡️ StateGuard Safety Proof
- ✅ **Pre-Commit Invariants:** Passed (`peak_cpu_percent` = 42.1% ≤ 80%)
- ✅ **Drift Detector:** Passed (Cost Z-Score = 0.82 ≤ 3.5)
- ✅ **Security Compliance:** Passed (Storage encryption & SOC 2 tags verified)
```
