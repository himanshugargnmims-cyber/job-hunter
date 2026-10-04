#!/usr/bin/env python3
"""
web_ui.py - Standalone Web UI & Onboarding Dashboard for Job Hunter

Provides a clean browser interface:
1. Drag-and-drop or select candidate resume (PDF or TXT).
2. Auto-extracts contact details, links, and background highlights via Python.
3. Form to review and customize all candidate screening variables and search preferences.
4. One-click save and pipeline launcher.
"""

import os
import sys
import re
import json
import cgi
import io
import subprocess
import threading
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

BASE_DIR = Path(__file__).resolve().parent.parent
CONTEXT_DIR = BASE_DIR / "context"
RESUMES_DIR = BASE_DIR / "resumes"
DATA_DIR = BASE_DIR / "data"

for d in [CONTEXT_DIR, RESUMES_DIR, DATA_DIR]:
    d.mkdir(parents=True, exist_ok=True)

HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Job Hunter — Setup & Application Launchpad</title>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #0f172a;
      --card-bg: #1e293b;
      --card-border: #334155;
      --primary: #3b82f6;
      --primary-hover: #2563eb;
      --accent: #10b981;
      --text: #f8fafc;
      --text-muted: #94a3b8;
      --danger: #ef4444;
      --input-bg: #0f172a;
      --font: 'Inter', -apple-system, sans-serif;
      --mono: 'JetBrains Mono', monospace;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: var(--bg);
      color: var(--text);
      font-family: var(--font);
      line-height: 1.5;
      padding: 30px 20px;
    }
    .container {
      max-width: 960px;
      margin: 0 auto;
    }
    header {
      text-align: center;
      margin-bottom: 35px;
    }
    .badge {
      display: inline-block;
      background: rgba(59, 130, 246, 0.15);
      color: #60a5fa;
      padding: 4px 12px;
      border-radius: 9999px;
      font-size: 0.8rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      margin-bottom: 12px;
      border: 1px solid rgba(59, 130, 246, 0.3);
    }
    h1 {
      font-size: 2.2rem;
      font-weight: 700;
      letter-spacing: -0.02em;
      margin-bottom: 8px;
    }
    .subtitle {
      color: var(--text-muted);
      font-size: 1.05rem;
    }
    .card {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 12px;
      padding: 24px;
      margin-bottom: 24px;
      box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2);
    }
    .card-title {
      font-size: 1.25rem;
      font-weight: 600;
      margin-bottom: 6px;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .card-subtitle {
      color: var(--text-muted);
      font-size: 0.9rem;
      margin-bottom: 20px;
    }
    .dropzone {
      border: 2px dashed #475569;
      border-radius: 10px;
      padding: 30px 20px;
      text-align: center;
      cursor: pointer;
      transition: all 0.2s ease;
      background: rgba(15, 23, 42, 0.5);
    }
    .dropzone:hover, .dropzone.dragover {
      border-color: var(--primary);
      background: rgba(59, 130, 246, 0.05);
    }
    .dropzone-icon {
      font-size: 2rem;
      margin-bottom: 10px;
    }
    .file-input { display: none; }
    .grid-2 {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 16px;
    }
    .grid-3 {
      display: grid;
      grid-template-columns: 1fr 1fr 1fr;
      gap: 16px;
    }
    @media (max-width: 640px) {
      .grid-2, .grid-3 { grid-template-columns: 1fr; }
    }
    .form-group {
      margin-bottom: 16px;
    }
    label {
      display: block;
      font-size: 0.85rem;
      font-weight: 500;
      color: var(--text-muted);
      margin-bottom: 6px;
    }
    input[type="text"], input[type="email"], input[type="number"], select, textarea {
      width: 100%;
      background: var(--input-bg);
      border: 1px solid var(--card-border);
      color: var(--text);
      padding: 10px 14px;
      border-radius: 8px;
      font-family: inherit;
      font-size: 0.95rem;
      transition: border-color 0.2s;
    }
    input:focus, select:focus, textarea:focus {
      outline: none;
      border-color: var(--primary);
      box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2);
    }
    textarea { resize: vertical; min-height: 80px; }
    .btn-group {
      display: flex;
      gap: 14px;
      margin-top: 10px;
    }
    button {
      padding: 12px 24px;
      border-radius: 8px;
      font-size: 1rem;
      font-weight: 600;
      cursor: pointer;
      border: none;
      transition: all 0.2s;
    }
    .btn-primary {
      background: var(--primary);
      color: white;
      flex: 1;
    }
    .btn-primary:hover { background: var(--primary-hover); }
    .btn-secondary {
      background: #334155;
      color: white;
    }
    .btn-secondary:hover { background: #475569; }
    .btn-accent {
      background: var(--accent);
      color: white;
      flex: 1;
    }
    .btn-accent:hover { background: #059669; }
    #status-banner {
      display: none;
      padding: 14px 18px;
      border-radius: 8px;
      margin-bottom: 20px;
      font-weight: 500;
    }
    .banner-success { background: rgba(16, 185, 129, 0.2); border: 1px solid var(--accent); color: #34d399; }
    .banner-error { background: rgba(239, 68, 68, 0.2); border: 1px solid var(--danger); color: #f87171; }
    .log-box {
      background: #090d16;
      border: 1px solid var(--card-border);
      border-radius: 8px;
      padding: 16px;
      font-family: var(--mono);
      font-size: 0.85rem;
      color: #38bdf8;
      max-height: 250px;
      overflow-y: auto;
      white-space: pre-wrap;
      display: none;
    }
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div class="badge">Open Source Job Hunter</div>
      <h1>Job Hunter Configuration Launchpad</h1>
      <p class="subtitle">Upload your resume, customize your target variables, and start automated job searching.</p>
    </header>

    <!-- RevOps & Pipeline Intelligence Scorecard -->
    <div class="card" style="background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%); border-left: 4px solid #3b82f6;">
      <div class="card-title">📈 RevOps & Pipeline Telemetry Command Center</div>
      <div class="card-subtitle">Real-time GTM velocity, forecast confidence, and opportunity acquisition metrics.</div>
      <div class="grid-3" style="margin-top: 15px;">
        <div style="background: rgba(15, 23, 42, 0.6); padding: 16px; border-radius: 8px; border: 1px solid #334155; text-align: center;">
          <div style="font-size: 0.8rem; color: #94a3b8; text-transform: uppercase;">Quarterly Revenue Velocity</div>
          <div style="font-size: 1.6rem; font-weight: 700; color: #38bdf8; margin-top: 4px;" id="kpi-velocity">$3.10M</div>
          <div style="font-size: 0.75rem; color: #34d399; margin-top: 2px;">+40.2% with RevOps levers</div>
        </div>
        <div style="background: rgba(15, 23, 42, 0.6); padding: 16px; border-radius: 8px; border: 1px solid #334155; text-align: center;">
          <div style="font-size: 0.8rem; color: #94a3b8; text-transform: uppercase;">Forecast Variance (MAPE)</div>
          <div style="font-size: 1.6rem; font-weight: 700; color: #34d399; margin-top: 4px;" id="kpi-mape">5.4%</div>
          <div style="font-size: 0.75rem; color: #94a3b8; margin-top: 2px;">Top-Decile Forecasting Rigor</div>
        </div>
        <div style="background: rgba(15, 23, 42, 0.6); padding: 16px; border-radius: 8px; border: 1px solid #334155; text-align: center;">
          <div style="font-size: 0.8rem; color: #94a3b8; text-transform: uppercase;">SaaS Magic Number & NRR</div>
          <div style="font-size: 1.6rem; font-weight: 700; color: #fbbf24; margin-top: 4px;" id="kpi-magic">1.25x / 115%</div>
          <div style="font-size: 0.75rem; color: #94a3b8; margin-top: 2px;">Hyper-Efficient Growth</div>
        </div>
      </div>
    </div>

    <!-- Step 1: Upload Resume -->
    <div class="card">
      <div class="card-title">📄 Step 1: Resume Upload & Auto-Detection</div>
      <div class="card-subtitle">Upload your resume (PDF or TXT). Key fields will be extracted automatically.</div>
      <div class="dropzone" id="dropzone" onclick="document.getElementById('file-input').click()">
        <div class="dropzone-icon">📥</div>
        <p><strong>Click to choose a file</strong> or drag and drop your resume PDF</p>
        <p style="color: var(--text-muted); font-size: 0.85rem; margin-top: 4px;">Supports .pdf, .txt</p>
      </div>
      <input type="file" id="file-input" class="file-input" accept=".pdf,.txt" onchange="uploadResume(this.files[0])">
      <p id="uploaded-filename" style="margin-top: 10px; font-size: 0.9rem; color: #60a5fa; font-weight: 500;"></p>
    </div>

    <!-- Step 2: Personal & Screening Variables -->
    <form id="config-form" onsubmit="saveConfiguration(event)">
      <div class="card">
        <div class="card-title">👤 Step 2: Candidate Details & Screening Variables</div>
        <div class="card-subtitle">These details auto-fill standard ATS forms (Greenhouse, Lever, Ashby, LinkedIn).</div>
        
        <div class="grid-2">
          <div class="form-group">
            <label>Full Name</label>
            <input type="text" id="full_name" name="full_name" placeholder="Alex Taylor" required>
          </div>
          <div class="form-group">
            <label>Email Address</label>
            <input type="email" id="email" name="email" placeholder="alex@example.com" required>
          </div>
        </div>

        <div class="grid-2">
          <div class="form-group">
            <label>Phone Number (with Country Code)</label>
            <input type="text" id="phone" name="phone" placeholder="+1 555-0199" required>
          </div>
          <div class="form-group">
            <label>Current Location (City, Country)</label>
            <input type="text" id="location" name="location" placeholder="San Francisco, CA, USA" required>
          </div>
        </div>

        <div class="grid-2">
          <div class="form-group">
            <label>Willing to Relocate?</label>
            <input type="text" id="willing_to_relocate" name="willing_to_relocate" placeholder="Yes (Remote, New York, London)">
          </div>
          <div class="form-group">
            <label>Work Authorization / Citizenship</label>
            <input type="text" id="work_authorization" name="work_authorization" placeholder="Authorized to work / Citizen">
          </div>
        </div>

        <div class="grid-2">
          <div class="form-group">
            <label>Requires Visa Sponsorship?</label>
            <select id="requires_sponsorship" name="requires_sponsorship">
              <option value="No">No</option>
              <option value="Yes">Yes</option>
            </select>
          </div>
          <div class="form-group">
            <label>Notice Period</label>
            <input type="text" id="notice_period" name="notice_period" placeholder="Immediate / 30 Days">
          </div>
        </div>

        <div class="grid-3">
          <div class="form-group">
            <label>Current / Recent Company</label>
            <input type="text" id="current_company" name="current_company" placeholder="Acme Inc">
          </div>
          <div class="form-group">
            <label>Current / Recent Title</label>
            <input type="text" id="current_title" name="current_title" placeholder="Senior Operations Lead">
          </div>
          <div class="form-group">
            <label>Total Experience (Years)</label>
            <input type="number" id="total_years_experience" name="total_years_experience" placeholder="6">
          </div>
        </div>

        <div class="grid-2">
          <div class="form-group">
            <label>Current CTC / Salary (Digits)</label>
            <input type="text" id="current_ctc" name="current_ctc" placeholder="4000000">
          </div>
          <div class="form-group">
            <label>Expected CTC / Salary (Digits)</label>
            <input type="text" id="expected_ctc" name="expected_ctc" placeholder="5500000">
          </div>
        </div>

        <div class="grid-2">
          <div class="form-group">
            <label>LinkedIn URL</label>
            <input type="text" id="linkedin_url" name="linkedin_url" placeholder="https://linkedin.com/in/username">
          </div>
          <div class="form-group">
            <label>GitHub / Portfolio URL</label>
            <input type="text" id="github_url" name="github_url" placeholder="https://github.com/username">
          </div>
        </div>

        <div class="form-group">
          <label>Executive Profile Pitch / Narrative (Grounded context for custom questions)</label>
          <textarea id="summary" name="summary" placeholder="Accomplished cross-functional operations leader..."></textarea>
        </div>
      </div>

      <!-- Step 3: Job Search Preferences -->
      <div class="card">
        <div class="card-title">🎯 Step 3: Search Preferences & Filtering Rules</div>
        <div class="card-subtitle">Define target titles, hubs, salary floor, and negative exclusion keywords.</div>
        
        <div class="form-group">
          <label>Target Job Titles (comma-separated)</label>
          <input type="text" id="target_roles" name="target_roles" placeholder="Chief of Staff, Strategy & Operations, Program Manager">
        </div>

        <div class="form-group">
          <label>Target Locations (comma-separated)</label>
          <input type="text" id="target_locations" name="target_locations" placeholder="Remote, Global Remote, San Francisco, New York, Bengaluru">
        </div>

        <div class="grid-3">
          <div class="form-group">
            <label>Min Salary Floor (INR LPA)</label>
            <input type="number" step="0.1" id="min_salary_floor_lpa" name="min_salary_floor_lpa" value="30.0">
          </div>
          <div class="form-group">
            <label>Min Salary Floor (USD)</label>
            <input type="number" step="1000" id="min_salary_floor_usd" name="min_salary_floor_usd" value="60000">
          </div>
          <div class="form-group">
            <label>Min Fit Score (0-100%)</label>
            <input type="number" id="minimum_match_score" name="minimum_match_score" value="70">
          </div>
        </div>

        <div class="form-group">
          <label>Excluded Keywords (comma-separated, auto-reject roles containing these)</label>
          <input type="text" id="excluded_keywords" name="excluded_keywords" placeholder="Intern, Software Engineer, QA, Recruiter">
        </div>

        <div class="form-group">
          <label>Target Companies (ATS Slugs for Greenhouse / Lever / Ashby, comma-separated)</label>
          <textarea id="target_companies" name="target_companies" placeholder="gitlab, stripe, ramp, databricks, replit, perplexity"></textarea>
        </div>
      </div>

      <!-- Step 4: AI & Settings -->
      <div class="card">
        <div class="card-title">⚙️ Step 4: Automation & AI Credentials</div>
        <div class="card-subtitle">Configure optional Gemini AI for smart screening answering and browser modes.</div>
        
        <div class="grid-2">
          <div class="form-group">
            <label>Google Gemini API Key (Optional)</label>
            <input type="text" id="gemini_api_key" name="gemini_api_key" placeholder="AIzaSy...">
          </div>
          <div class="form-group">
            <label>Browser Visibility</label>
            <select id="headless" name="headless">
              <option value="false">Visible Browser (Watch live applications)</option>
              <option value="true">Headless (Silent background execution)</option>
            </select>
          </div>
        </div>

        <div class="btn-group">
          <button type="submit" class="btn-primary">💾 Save Profile & Preferences</button>
          <button type="button" class="btn-accent" onclick="startPipeline()">🚀 Launch Job Hunter Pipeline</button>
        </div>
      </div>
    </form>

    <div class="card" id="log-card" style="display: none;">
      <div class="card-title">📡 Real-Time Execution Console</div>
      <div class="log-box" id="log-box"></div>
    </div>
  </div>

  <script>
    // Load initial configuration on page load
    window.addEventListener('DOMContentLoaded', async () => {
      try {
        const res = await fetch('/api/get_config');
        if (res.ok) {
          const data = await res.json();
          populateForm(data);
        }
      } catch (e) {
        console.error("Config load error:", e);
      }

      try {
        const revRes = await fetch('/api/get_revops_metrics');
        if (revRes.ok) {
          const revData = await revRes.json();
          if (revData.success) {
            document.getElementById('kpi-velocity').innerText = '$' + (revData.velocity.quarterly_revenue_velocity / 1000000).toFixed(2) + 'M';
            document.getElementById('kpi-mape').innerText = revData.mape + '%';
            document.getElementById('kpi-magic').innerText = revData.kpis.magic_number + 'x / ' + revData.kpis.net_retention_rate_pct + '%';
          }
        }
      } catch (e) {
        console.error("RevOps metrics load error:", e);
      }
    });

    function populateForm(data) {
      if (!data) return;
      const qa = data.screening_qa || {};
      const pref = data.preferences || {};
      const ans = qa.screening_answers || {};

      document.getElementById('full_name').value = qa.full_name || '';
      document.getElementById('email').value = qa.email || '';
      document.getElementById('phone').value = qa.phone || '';
      document.getElementById('location').value = qa.location || '';
      document.getElementById('willing_to_relocate').value = qa.willing_to_relocate || '';
      document.getElementById('work_authorization').value = qa.work_authorization || '';
      document.getElementById('requires_sponsorship').value = qa.requires_sponsorship || 'No';
      document.getElementById('notice_period').value = qa.current_notice_period || '';
      document.getElementById('linkedin_url').value = qa.linkedin_url || '';
      document.getElementById('github_url').value = qa.github_portfolio_url || '';

      document.getElementById('current_company').value = ans.current_company || '';
      document.getElementById('current_title').value = ans.current_title || '';
      document.getElementById('total_years_experience').value = ans.total_years_experience || '5';
      document.getElementById('current_ctc').value = ans.current_ctc || '';
      document.getElementById('expected_ctc').value = ans.expected_ctc || '';
      document.getElementById('summary').value = ans.summary || '';

      if (pref.target_roles) document.getElementById('target_roles').value = pref.target_roles.join(', ');
      if (pref.target_locations) document.getElementById('target_locations').value = pref.target_locations.join(', ');
      if (pref.min_salary_floor_lpa) document.getElementById('min_salary_floor_lpa').value = pref.min_salary_floor_lpa;
      if (pref.min_salary_floor_usd) document.getElementById('min_salary_floor_usd').value = pref.min_salary_floor_usd;
      if (pref.minimum_match_score) document.getElementById('minimum_match_score').value = pref.minimum_match_score;
      if (pref.excluded_keywords) document.getElementById('excluded_keywords').value = pref.excluded_keywords.join(', ');
      if (data.target_companies) document.getElementById('target_companies').value = data.target_companies.join(', ');
      if (data.gemini_api_key) document.getElementById('gemini_api_key').value = data.gemini_api_key;
    }

    async function uploadResume(file) {
      if (!file) return;
      showBanner("Uploading and analyzing resume...", false);
      const formData = new FormData();
      formData.append('resume', file);

      try {
        const res = await fetch('/api/upload_resume', {
          method: 'POST',
          body: formData
        });
        const result = await res.json();
        if (result.success) {
          document.getElementById('uploaded-filename').innerText = `✓ Loaded: ${file.name}`;
          if (result.detected) {
            if (result.detected.full_name) document.getElementById('full_name').value = result.detected.full_name;
            if (result.detected.email) document.getElementById('email').value = result.detected.email;
            if (result.detected.phone) document.getElementById('phone').value = result.detected.phone;
            if (result.detected.linkedin_url) document.getElementById('linkedin_url').value = result.detected.linkedin_url;
            if (result.detected.github_url) document.getElementById('github_url').value = result.detected.github_url;
          }
          showBanner("Resume parsed successfully! Review the extracted fields below.", true);
        } else {
          showBanner("Error parsing resume: " + (result.error || "Unknown"), false);
        }
      } catch (e) {
        showBanner("Upload failed: " + e.message, false);
      }
    }

    async function saveConfiguration(event) {
      if (event) event.preventDefault();
      showBanner("Saving configuration...", false);

      const payload = {
        full_name: document.getElementById('full_name').value,
        email: document.getElementById('email').value,
        phone: document.getElementById('phone').value,
        location: document.getElementById('location').value,
        willing_to_relocate: document.getElementById('willing_to_relocate').value,
        work_authorization: document.getElementById('work_authorization').value,
        requires_sponsorship: document.getElementById('requires_sponsorship').value,
        notice_period: document.getElementById('notice_period').value,
        linkedin_url: document.getElementById('linkedin_url').value,
        github_url: document.getElementById('github_url').value,
        current_company: document.getElementById('current_company').value,
        current_title: document.getElementById('current_title').value,
        total_years_experience: document.getElementById('total_years_experience').value,
        current_ctc: document.getElementById('current_ctc').value,
        expected_ctc: document.getElementById('expected_ctc').value,
        summary: document.getElementById('summary').value,
        target_roles: document.getElementById('target_roles').value.split(',').map(s => s.trim()).filter(Boolean),
        target_locations: document.getElementById('target_locations').value.split(',').map(s => s.trim()).filter(Boolean),
        min_salary_floor_lpa: parseFloat(document.getElementById('min_salary_floor_lpa').value) || 30.0,
        min_salary_floor_usd: parseFloat(document.getElementById('min_salary_floor_usd').value) || 60000.0,
        minimum_match_score: parseInt(document.getElementById('minimum_match_score').value) || 70,
        excluded_keywords: document.getElementById('excluded_keywords').value.split(',').map(s => s.trim()).filter(Boolean),
        target_companies: document.getElementById('target_companies').value.split(',').map(s => s.trim()).filter(Boolean),
        gemini_api_key: document.getElementById('gemini_api_key').value,
        headless: document.getElementById('headless').value
      };

      try {
        const res = await fetch('/api/save_config', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        const result = await res.json();
        if (result.success) {
          showBanner("🎉 Configuration saved successfully! You are ready to start searching.", true);
        } else {
          showBanner("Save failed: " + result.error, false);
        }
      } catch (e) {
        showBanner("Error saving: " + e.message, false);
      }
    }

    async function startPipeline() {
      await saveConfiguration(null);
      showBanner("🚀 Job Hunter pipeline launched! Streaming console logs...", true);
      document.getElementById('log-card').style.display = 'block';
      const logBox = document.getElementById('log-box');
      logBox.style.display = 'block';
      logBox.innerText = "Initializing pipeline runner...\\n";

      try {
        const res = await fetch('/api/start_pipeline', { method: 'POST' });
        const result = await res.json();
        if (result.success) {
          pollLogs();
        }
      } catch (e) {
        logBox.innerText += "\\nError launching: " + e.message;
      }
    }

    function pollLogs() {
      const interval = setInterval(async () => {
        try {
          const res = await fetch('/api/get_logs');
          if (res.ok) {
            const data = await res.json();
            const logBox = document.getElementById('log-box');
            logBox.innerText = data.logs;
            logBox.scrollTop = logBox.scrollHeight;
            if (data.is_done) {
              clearInterval(interval);
              showBanner("✅ Application pipeline completed!", true);
            }
          }
        } catch (e) {
          console.error("Log poll error", e);
        }
      }, 2000);
    }

    function showBanner(msg, isSuccess) {
      const b = document.getElementById('status-banner');
      b.style.display = 'block';
      b.className = isSuccess ? 'banner-success' : 'banner-error';
      b.innerText = msg;
    }
  </script>
</body>
</html>
"""

latest_logs = []
pipeline_running = False


class JobHunterHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Suppress default request logs for clean terminal

    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/" or url.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode("utf-8"))
        elif url.path == "/api/get_config":
            self.handle_get_config()
        elif url.path == "/api/get_revops_metrics":
            self.handle_get_revops_metrics()
        elif url.path == "/api/get_logs":
            self.handle_get_logs()
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        url = urlparse(self.path)
        if url.path == "/api/upload_resume":
            self.handle_upload_resume()
        elif url.path == "/api/save_config":
            self.handle_save_config()
        elif url.path == "/api/start_pipeline":
            self.handle_start_pipeline()
        else:
            self.send_response(404)
            self.end_headers()

    def handle_get_config(self):
        from setup_profile import parse_resume_heuristics
        
        qa_file = CONTEXT_DIR / "screening_qa.json"
        pref_file = CONTEXT_DIR / "preferences.json"
        comp_file = CONTEXT_DIR / "company_list.txt"

        data = {"screening_qa": {}, "preferences": {}, "target_companies": [], "gemini_api_key": os.getenv("GEMINI_API_KEY", "")}
        if qa_file.exists():
            try:
                data["screening_qa"] = json.loads(qa_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        if pref_file.exists():
            try:
                data["preferences"] = json.loads(pref_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        if comp_file.exists():
            data["target_companies"] = [l.strip() for l in comp_file.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")]

        self.send_json(data)

    def handle_get_revops_metrics(self):
        try:
            sys.path.insert(0, str(BASE_DIR))
            from revops_kit.forecasting_engine import RevenueForecaster
            from revops_kit.pipeline_velocity import PipelineVelocityCalculator
            from revops_kit.executive_kpi_dashboard import ExecutiveDashboardGenerator

            forecaster = RevenueForecaster(target_quarterly_quota=4000000.0)
            deals = [
                {"name": "Enterprise Cloud Migration", "acv": 850000, "stage": "Stage 5 - Security & Legal Review", "category": "Commit"},
                {"name": "FinTech Core Modernization", "acv": 1200000, "stage": "Stage 4 - Business Proposal & Pricing", "category": "Best Case"},
                {"name": "Global Payments Rollout", "acv": 1500000, "stage": "Stage 6 - Closed Won", "category": "Closed Won"},
                {"name": "SaaS Platform Expansion", "acv": 450000, "stage": "Stage 3 - Technical Validation / POC", "category": "Pipeline"},
            ]
            f_res = forecaster.compute_weighted_pipeline(deals)
            mape = forecaster.calculate_mape([3200000, 3600000, 3400000, 3900000], [3450000, 3800000, 3550000, 4050000])

            vel_calc = PipelineVelocityCalculator(num_opportunities=95, win_rate_pct=26.0, avg_deal_size=88000.0, sales_cycle_days=64)
            vel = vel_calc.calculate_velocity()
            sim = vel_calc.simulate_revops_interventions()

            dash_gen = ExecutiveDashboardGenerator()
            kpis = dash_gen.compute_saas_metrics()

            self.send_json({
                "success": True,
                "forecast": f_res,
                "mape": mape,
                "velocity": vel,
                "simulations": sim,
                "kpis": kpis
            })
        except Exception as e:
            self.send_json({"success": False, "error": str(e)})

    def handle_upload_resume(self):
        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            self.send_json({"success": False, "error": "Invalid Content-Type"})
            return

        from setup_profile import extract_text_from_file, parse_resume_heuristics

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        # Parse multipart form data
        boundary = content_type.split("boundary=")[-1].encode()
        parts = body.split(b"--" + boundary)
        
        saved_file = None
        for p in parts:
            if b'filename="' in p:
                header_part, file_data = p.split(b"\r\n\r\n", 1)
                file_data = file_data.rsplit(b"\r\n", 1)[0]
                filename_match = re.search(r'filename="([^"]+)"', header_part.decode(errors="ignore"))
                filename = filename_match.group(1) if filename_match else "resume.pdf"
                saved_file = RESUMES_DIR / filename
                saved_file.write_bytes(file_data)
                break

        if saved_file and saved_file.exists():
            text = extract_text_from_file(saved_file)
            detected = parse_resume_heuristics(text)
            self.send_json({"success": True, "filename": saved_file.name, "detected": detected})
        else:
            self.send_json({"success": False, "error": "File could not be saved"})

    def handle_save_config(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        data = json.loads(body.decode("utf-8"))

        full_name = data.get("full_name", "")
        parts = full_name.split()
        first_name = parts[0] if parts else ""
        last_name = parts[-1] if len(parts) > 1 else ""

        # 1. context/screening_qa.json
        qa_data = {
            "full_name": full_name,
            "first_name": first_name,
            "last_name": last_name,
            "email": data.get("email", ""),
            "phone": data.get("phone", ""),
            "location": data.get("location", ""),
            "willing_to_relocate": data.get("willing_to_relocate", ""),
            "work_authorization": data.get("work_authorization", ""),
            "requires_sponsorship": data.get("requires_sponsorship", "No"),
            "current_notice_period": data.get("notice_period", "30 Days"),
            "linkedin_url": data.get("linkedin_url", ""),
            "github_portfolio_url": data.get("github_url", ""),
            "screening_answers": {
                "notice_period": data.get("notice_period", "30 Days"),
                "work_authorization": data.get("work_authorization", ""),
                "relocation": data.get("willing_to_relocate", ""),
                "current_company": data.get("current_company", ""),
                "current_title": data.get("current_title", ""),
                "total_years_experience": int(data.get("total_years_experience", 5)),
                "current_ctc": data.get("current_ctc", ""),
                "expected_ctc": data.get("expected_ctc", ""),
                "summary": data.get("summary", "")
            }
        }
        (CONTEXT_DIR / "screening_qa.json").write_text(json.dumps(qa_data, indent=2), encoding="utf-8")

        # 2. context/preferences.json
        pref_data = {
            "target_roles": data.get("target_roles", []),
            "target_locations": data.get("target_locations", []),
            "experience_years_min": max(1, int(data.get("total_years_experience", 5)) - 3),
            "experience_years_max": int(data.get("total_years_experience", 5)) + 4,
            "minimum_match_score": int(data.get("minimum_match_score", 70)),
            "min_salary_floor_lpa": float(data.get("min_salary_floor_lpa", 30.0)),
            "min_salary_floor_usd": float(data.get("min_salary_floor_usd", 60000.0)),
            "excluded_keywords": data.get("excluded_keywords", [])
        }
        (CONTEXT_DIR / "preferences.json").write_text(json.dumps(pref_data, indent=2), encoding="utf-8")

        # 3. context/company_list.txt
        companies = data.get("target_companies", [])
        (CONTEXT_DIR / "company_list.txt").write_text("# Target ATS Companies\n" + "\n".join(companies) + "\n", encoding="utf-8")

        # 4. context/profile_notes.md
        profile_notes = f"""# Candidate Profile: {full_name}
- Email: {data.get('email')} | Phone: {data.get('phone')}
- Location: {data.get('location')} | Relocation: {data.get('willing_to_relocate')}
- LinkedIn: {data.get('linkedin_url')}
- Role: {data.get('current_title')} @ {data.get('current_company')} ({data.get('total_years_experience')} yrs exp)

## Summary
{data.get('summary')}
"""
        (CONTEXT_DIR / "profile_notes.md").write_text(profile_notes, encoding="utf-8")

        # 5. .env
        env_content = f"""HEADLESS={data.get('headless', 'false').lower()}
GEMINI_API_KEY={data.get('gemini_api_key', '')}
MIN_SALARY_FLOOR_LPA={data.get('min_salary_floor_lpa', 30.0)}
MIN_SALARY_FLOOR_USD={data.get('min_salary_floor_usd', 60000.0)}
MIN_FIT_SCORE={data.get('minimum_match_score', 70)}
"""
        (BASE_DIR / ".env").write_text(env_content, encoding="utf-8")

        self.send_json({"success": True})

    def handle_start_pipeline(self):
        global pipeline_running, latest_logs
        if pipeline_running:
            self.send_json({"success": True, "message": "Already running"})
            return

        pipeline_running = True
        latest_logs = ["Launching Job Hunter orchestrator pipeline...\n"]

        def run_proc():
            global pipeline_running, latest_logs
            try:
                cmd = [sys.executable, str(BASE_DIR / "run.py"), "--all"]
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=str(BASE_DIR))
                for line in proc.stdout:
                    latest_logs.append(line)
                    if len(latest_logs) > 300:
                        latest_logs = latest_logs[-300:]
                proc.wait()
                latest_logs.append("\n[Finished] Job Hunter pipeline complete.\n")
            except Exception as e:
                latest_logs.append(f"\n[Execution Error]: {e}\n")
            finally:
                pipeline_running = False

        t = threading.Thread(target=run_proc, daemon=True)
        t.start()
        self.send_json({"success": True})

    def handle_get_logs(self):
        self.send_json({"logs": "".join(latest_logs), "is_done": not pipeline_running})

    def send_json(self, data: dict):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))


def start_server(port: int = 8080):
    server_address = ("127.0.0.1", port)
    try:
        httpd = HTTPServer(server_address, JobHunterHandler)
    except OSError:
        server_address = ("127.0.0.1", port + 1)
        httpd = HTTPServer(server_address, JobHunterHandler)

    print("\n" + "=" * 60)
    print(f"🚀 Job Hunter Web UI running at: http://{server_address[0]}:{server_address[1]}")
    print("=" * 60)
    print("Open this URL in your web browser to upload your resume & configure variables.\n")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Web UI server.")
        httpd.server_close()


if __name__ == "__main__":
    start_server()
