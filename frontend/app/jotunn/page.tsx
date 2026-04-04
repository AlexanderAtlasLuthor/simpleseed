'use client';

import { useEffect, useRef, useState } from 'react';
import './jotunn.css';

export default function JotunnPage() {
  const cursorRef = useRef<HTMLDivElement>(null);
  const ringRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [formSent, setFormSent] = useState(false);

  // Custom cursor
  useEffect(() => {
    const cur = cursorRef.current;
    const ring = ringRef.current;
    if (!cur || !ring) return;

    const onMove = (e: MouseEvent) => {
      cur.style.left = e.clientX + 'px';
      cur.style.top = e.clientY + 'px';
      ring.style.left = e.clientX + 'px';
      ring.style.top = e.clientY + 'px';
    };
    document.addEventListener('mousemove', onMove);

    const hoverEls = document.querySelectorAll('a, button, .svc-card, .why-card');
    const enter = () => {
      cur.style.width = '14px'; cur.style.height = '14px';
      ring.style.width = '46px'; ring.style.height = '46px';
      ring.style.borderColor = 'rgba(126,207,255,0.65)';
    };
    const leave = () => {
      cur.style.width = '8px'; cur.style.height = '8px';
      ring.style.width = '30px'; ring.style.height = '30px';
      ring.style.borderColor = 'rgba(126,207,255,0.35)';
    };
    hoverEls.forEach(el => { el.addEventListener('mouseenter', enter); el.addEventListener('mouseleave', leave); });

    return () => {
      document.removeEventListener('mousemove', onMove);
      hoverEls.forEach(el => { el.removeEventListener('mouseenter', enter); el.removeEventListener('mouseleave', leave); });
    };
  }, []);

  // Canvas animation
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d')!;
    let W = 0, H = 0;
    let animId: number;

    function resize() { W = canvas!.width = window.innerWidth; H = canvas!.height = window.innerHeight; }
    resize();
    window.addEventListener('resize', resize);

    const stars = Array.from({ length: 260 }, () => ({
      x: Math.random() * 1920, y: Math.random() * 1080,
      r: Math.random() * 1.1 + 0.2,
      op: Math.random() * 0.3 + 0.04,
      tw: Math.random() * 0.007 + 0.002,
      td: Math.random() > 0.5 ? 1 : -1,
      vy: -(Math.random() * 0.12 + 0.03),
      vx: (Math.random() - 0.5) * 0.06,
      a: Math.random() * Math.PI * 2,
    }));

    const flakes = Array.from({ length: 22 }, () => ({
      x: Math.random() * 1920, y: Math.random() * 1080,
      size: Math.random() * 12 + 4,
      op: Math.random() * 0.10 + 0.02,
      drift: (Math.random() - 0.5) * 0.14,
      fall: Math.random() * 0.18 + 0.04,
    }));

    function snowflake(x: number, y: number, size: number, alpha: number) {
      ctx.save();
      ctx.translate(x, y);
      ctx.strokeStyle = `rgba(200,230,255,${alpha})`;
      ctx.lineWidth = 0.45;
      for (let i = 0; i < 6; i++) {
        ctx.beginPath();
        ctx.moveTo(0, 0); ctx.lineTo(0, size);
        ctx.moveTo(0, size * 0.38); ctx.lineTo(size * 0.18, size * 0.52);
        ctx.moveTo(0, size * 0.38); ctx.lineTo(-size * 0.18, size * 0.52);
        ctx.moveTo(0, size * 0.65); ctx.lineTo(size * 0.12, size * 0.76);
        ctx.moveTo(0, size * 0.65); ctx.lineTo(-size * 0.12, size * 0.76);
        ctx.stroke();
        ctx.rotate(Math.PI / 3);
      }
      ctx.restore();
    }

    function loop() {
      ctx.clearRect(0, 0, W, H);
      stars.forEach(p => {
        p.op += p.tw * p.td;
        if (p.op > 0.38 || p.op < 0.02) p.td *= -1;
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(200,228,255,${p.op})`;
        ctx.fill();
        p.y += p.vy; p.x += p.vx + Math.sin(p.a) * 0.06; p.a += 0.01;
        if (p.y < -10) { p.y = H + 10; p.x = Math.random() * W; }
      });
      flakes.forEach(f => {
        snowflake(f.x, f.y, f.size, f.op);
        f.y += f.fall; f.x += f.drift;
        if (f.y > H + 20) { f.y = -20; f.x = Math.random() * W; }
      });
      animId = requestAnimationFrame(loop);
    }
    loop();

    return () => {
      window.removeEventListener('resize', resize);
      cancelAnimationFrame(animId);
    };
  }, []);

  // Scroll reveal
  useEffect(() => {
    const obs = new IntersectionObserver(entries => {
      entries.forEach(e => { if (e.isIntersecting) e.target.classList.add('visible'); });
    }, { threshold: 0.1 });
    document.querySelectorAll('.reveal').forEach(el => obs.observe(el));
    return () => obs.disconnect();
  }, []);

  return (
    <div className="jotunn-root">
      <canvas className="jotunn-canvas" ref={canvasRef} />
      <div className="jotunn-cursor" ref={cursorRef} />
      <div className="jotunn-cursor-ring" ref={ringRef} />

      <div className="jotunn-page">

        {/* NAV */}
        <nav className="jotunn-nav">
          <a className="nav-logo" href="#hero">
            <svg className="nav-logo-svg" viewBox="0 0 100 100" fill="none">
              <polygon points="50,6 61,36 93,36 68,55 77,85 50,66 23,85 32,55 7,36 39,36" fill="none" stroke="rgba(200,235,255,0.75)" strokeWidth="2.2" strokeLinejoin="round"/>
              <circle cx="50" cy="50" r="16" fill="none" stroke="rgba(126,207,255,0.5)" strokeWidth="1.5"/>
              <circle cx="50" cy="50" r="5" fill="rgba(126,207,255,0.8)"/>
              <polygon points="50,2 54,12 50,18 46,12" fill="none" stroke="rgba(220,245,255,0.8)" strokeWidth="1.5"/>
              <polygon points="93,33 97,43 87,43" fill="none" stroke="rgba(220,245,255,0.8)" strokeWidth="1.5"/>
              <polygon points="7,33 3,43 13,43" fill="none" stroke="rgba(220,245,255,0.8)" strokeWidth="1.5"/>
            </svg>
            <span className="nav-wordmark">Jötunn</span>
          </a>
          <ul className="nav-links">
            <li><a href="#services">Services</a></li>
            <li><a href="#bounty">Bug Bounty</a></li>
            <li><a href="#process">Process</a></li>
            <li><a href="#why">About</a></li>
          </ul>
          <a className="nav-cta" href="#contact">Get a Quote</a>
        </nav>

        {/* HERO */}
        <section className="jotunn-hero" id="hero">
          <div className="frost-circle fc1" />
          <div className="frost-circle fc2" />
          <div className="frost-circle fc3" />

          <p className="hero-tag">// Offensive Security &amp; Bug Bounty</p>

          <div className="hero-emblem">
            <svg viewBox="0 0 200 200" fill="none">
              <defs>
                <linearGradient id="ig1" x1="0%" y1="0%" x2="100%" y2="100%">
                  <stop offset="0%" stopColor="#e8f6ff" stopOpacity="0.95"/>
                  <stop offset="50%" stopColor="#7ecfff" stopOpacity="0.85"/>
                  <stop offset="100%" stopColor="#c0e8ff" stopOpacity="0.9"/>
                </linearGradient>
                <linearGradient id="ig2" x1="0%" y1="0%" x2="100%" y2="100%">
                  <stop offset="0%" stopColor="#5dffd8" stopOpacity="0.45"/>
                  <stop offset="100%" stopColor="#7ecfff" stopOpacity="0.28"/>
                </linearGradient>
              </defs>
              <polygon points="100,10 118,68 178,68 130,106 148,164 100,126 52,164 70,106 22,68 82,68" fill="none" stroke="url(#ig1)" strokeWidth="2.5" strokeLinejoin="round"/>
              <polygon points="100,2 107,22 100,32 93,22" fill="none" stroke="rgba(225,245,255,0.8)" strokeWidth="1.8"/>
              <polygon points="185,62 196,76 176,80 172,65" fill="none" stroke="rgba(225,245,255,0.7)" strokeWidth="1.5"/>
              <polygon points="15,62 4,76 24,80 28,65" fill="none" stroke="rgba(225,245,255,0.7)" strokeWidth="1.5"/>
              <polygon points="152,162 162,178 142,175 138,158" fill="none" stroke="rgba(225,245,255,0.7)" strokeWidth="1.5"/>
              <polygon points="48,162 38,178 58,175 62,158" fill="none" stroke="rgba(225,245,255,0.7)" strokeWidth="1.5"/>
              <polygon points="100,38 132,58 148,100 132,142 100,162 68,142 52,100 68,58" fill="rgba(126,207,255,0.04)" stroke="rgba(126,207,255,0.32)" strokeWidth="1.5"/>
              <line x1="100" y1="10" x2="100" y2="38" stroke="rgba(180,220,255,0.28)" strokeWidth="1"/>
              <line x1="178" y1="68" x2="148" y2="78" stroke="rgba(180,220,255,0.28)" strokeWidth="1"/>
              <line x1="148" y1="164" x2="132" y2="145" stroke="rgba(180,220,255,0.28)" strokeWidth="1"/>
              <line x1="52" y1="164" x2="68" y2="145" stroke="rgba(180,220,255,0.28)" strokeWidth="1"/>
              <line x1="22" y1="68" x2="52" y2="78" stroke="rgba(180,220,255,0.28)" strokeWidth="1"/>
              <circle cx="100" cy="100" r="24" fill="rgba(5,15,30,0.85)" stroke="rgba(126,207,255,0.38)" strokeWidth="1.5"/>
              <circle cx="100" cy="100" r="12" fill="url(#ig2)"/>
              <circle cx="100" cy="100" r="5" fill="rgba(126,207,255,0.9)"/>
            </svg>
          </div>

          <h1 className="jotunn-h1">JÖTUNN</h1>
          <span className="h1-sub">Cybersecurity</span>

          <p className="hero-desc">
            We find your vulnerabilities before the adversary does. Offensive security for regulated industries and active bug bounty participation across global programs.
          </p>

          <div className="hero-actions">
            <a className="btn-ice" href="#contact">Request an Assessment</a>
            <a className="btn-ghost-ice" href="#services">Our Services</a>
          </div>

          <div className="hero-stats">
            <div className="hstat"><span className="hstat-n">150+</span><span className="hstat-l">Vulnerabilities Found</span></div>
            <div className="hstat"><span className="hstat-n">P1/P2</span><span className="hstat-l">Critical Reports</span></div>
            <div className="hstat"><span className="hstat-n">72h</span><span className="hstat-l">Avg. Report Delivery</span></div>
            <div className="hstat"><span className="hstat-n">0</span><span className="hstat-l">Client Data Breaches</span></div>
          </div>
        </section>

        <div className="divider-line" />

        {/* SERVICES */}
        <section className="jotunn-section services-section" id="services">
          <div className="inner">
            <div className="svc-header reveal">
              <div>
                <span className="sec-tag">// 01 — Services</span>
                <h2 className="jotunn-h2">We attack.<br/>So you can defend.</h2>
              </div>
              <p className="jotunn-p">Every engagement delivers prioritized, actionable findings tied to real business risk — not just a list of CVEs.</p>
            </div>
            <div className="svc-grid reveal">
              {[
                { n: '01', title: 'Penetration Testing', desc: 'Controlled simulations of real-world attacks against your web apps, APIs, internal networks, and infrastructure.' },
                { n: '02', title: 'Vulnerability Assessment', desc: 'Systematic identification of weaknesses across your tech stack with CVSS scoring and a remediation roadmap.' },
                { n: '03', title: 'Secure Code Review', desc: 'Manual and automated source code auditing to catch security defects before they reach production.' },
                { n: '04', title: 'Red Team Operations', desc: 'Full-scope red team engagements simulating advanced threat actors targeting your people, processes, and technology.' },
                { n: '05', title: 'Regulated Industries', desc: 'Security assessments aligned to HIPAA, PCI-DSS, SOC 2, and Florida-specific compliance frameworks.' },
                { n: '06', title: 'Security Training', desc: 'Technical training for dev and IT teams in offensive techniques, secure development, and threat modeling.' },
              ].map(s => (
                <div className="svc-card" key={s.n}>
                  <div className="svc-card-top" />
                  <div className="svc-num">{s.n}</div>
                  <h3 className="jotunn-h3">{s.title}</h3>
                  <p className="jotunn-p">{s.desc}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <div className="divider-line" />

        {/* BUG BOUNTY */}
        <section className="jotunn-section bounty-section" id="bounty">
          <div className="inner">
            <div className="bounty-layout">
              <div className="reveal">
                <span className="sec-tag">// 02 — Bug Bounty</span>
                <h2 className="jotunn-h2">We hunt bugs.<br/>For a living.</h2>
                <p className="jotunn-p" style={{ marginBottom: '1.4rem' }}>Active participants on HackerOne, Bugcrowd, and Intigriti. Our track record of critical-severity findings on high-profile targets validates our methodology before we ever touch your system.</p>
                <p className="jotunn-p">Running a private program? We integrate directly into your responsible disclosure process with NDA coverage, defined timelines, and clear proof-of-concept deliverables.</p>
                <div className="bb-badges">
                  <span className="badge hi">HackerOne</span>
                  <span className="badge hi">Bugcrowd</span>
                  <span className="badge hi">Intigriti</span>
                  <span className="badge">Private Programs</span>
                  <span className="badge">Responsible Disclosure</span>
                </div>
              </div>
              <div className="terminal reveal">
                <div className="term-bar">
                  <span className="dot dot-r" /><span className="dot dot-y" /><span className="dot dot-g" />
                  <span className="term-title">jotunn :: recon v2.4</span>
                </div>
                <div className="tl"><span className="tc"># Target: api.target.com — full scope</span></div>
                <div className="tl">&nbsp;</div>
                <div className="tl"><span className="tp">$</span> <span className="to">./recon --mode passive --out subs.txt</span></div>
                <div className="tl"><span className="ta">[ INFO ]</span> <span className="to">312 subdomains enumerated</span></div>
                <div className="tl"><span className="ta">[ INFO ]</span> <span className="to">47 live hosts confirmed</span></div>
                <div className="tl">&nbsp;</div>
                <div className="tl"><span className="tp">$</span> <span className="to">./probe --fuzz auth --endpoints api_routes.txt</span></div>
                <div className="tl"><span className="tx">[ CRIT ]</span> <span className="to">IDOR @ /api/v2/account/{'{'}{'}'}id{'}'} — no ownership check</span></div>
                <div className="tl"><span className="tx">[ CRIT ]</span> <span className="to">JWT alg:none accepted — auth bypass confirmed</span></div>
                <div className="tl"><span className="tx">[ HIGH ]</span> <span className="to">SSRF via webhook param — AWS metadata exposed</span></div>
                <div className="tl">&nbsp;</div>
                <div className="tl"><span className="tp">$</span> <span className="to">./report --severity p1 --format cvss</span></div>
                <div className="tl"><span className="ts">[ DONE ]</span> <span className="to">CVSS scores: 9.8 / 8.6 / 8.1</span></div>
                <div className="tl"><span className="ts">[ DONE ]</span> <span className="to">Vendor notified — 72h SLA clock started</span></div>
                <div className="tl">&nbsp;</div>
                <div className="tl"><span className="tp">$</span> <span className="term-cursor" /></div>
              </div>
            </div>
          </div>
        </section>

        <div className="divider-line" />

        {/* PROCESS */}
        <section className="jotunn-section process-section" id="process">
          <div className="inner">
            <span className="sec-tag reveal">// 03 — Methodology</span>
            <h2 className="jotunn-h2 reveal">How we work</h2>
            <div className="proc-grid">
              {[
                { n: '01 — SCOPE', title: 'Scoping', desc: 'Rules of engagement, targets, timelines, and legal coverage defined before any activity begins.' },
                { n: '02 — RECON', title: 'Reconnaissance', desc: 'Passive and active intelligence on the attack surface: domains, IPs, technologies, personnel.' },
                { n: '03 — EXPLOIT', title: 'Exploitation', desc: 'Controlled testing of confirmed vulnerabilities with minimal production impact and full evidence capture.' },
                { n: '04 — REPORT', title: 'Reporting', desc: 'Executive and technical documentation with CVSS scores, reproduction steps, and prioritized recommendations.' },
                { n: '05 — RETEST', title: 'Verification', desc: 'Once patches are applied, we verify every finding is properly remediated. No additional charge.' },
              ].map(s => (
                <div className="proc-step reveal" key={s.n}>
                  <div className="proc-num">{s.n}</div>
                  <h3 className="jotunn-h3">{s.title}</h3>
                  <p className="jotunn-p">{s.desc}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <div className="divider-line" />

        {/* WHY */}
        <section className="jotunn-section why-section" id="why">
          <div className="inner">
            <span className="sec-tag reveal">// 04 — Why Jötunn</span>
            <h2 className="jotunn-h2 reveal">Built on real-world<br/>offensive experience</h2>
            <div className="why-grid reveal">
              {[
                { n: '01', title: 'Impact-Driven Findings', desc: "We don't deliver raw CVE lists. Every finding includes its real business impact and a clear path to remediation." },
                { n: '02', title: 'Florida & Regulated Markets', desc: 'Deep familiarity with the local regulatory landscape: healthcare, finance, government, and manufacturing in Florida.' },
                { n: '03', title: "Attacker's Mindset", desc: 'Our team comes from active bug bounty practice where results speak for themselves — no theoretical frameworks.' },
                { n: '04', title: 'Full Confidentiality', desc: 'NDA on every engagement. Your findings never leave the scope of the contract. Responsible disclosure guaranteed.' },
              ].map(c => (
                <div className="why-card" key={c.n}>
                  <span className="why-n">{c.n}</span>
                  <h3 className="jotunn-h3">{c.title}</h3>
                  <p className="jotunn-p">{c.desc}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <div className="divider-line" />

        {/* CONTACT */}
        <section className="jotunn-section contact-section" id="contact">
          <div className="inner">
            <div className="contact-layout">
              <div className="reveal">
                <span className="sec-tag">// 05 — Contact</span>
                <h2 className="jotunn-h2">Start your<br/>assessment</h2>
                <p className="jotunn-p" style={{ marginBottom: '3rem' }}>A specialist will reach out within 24 business hours to discuss scope, timeline, and pricing for your engagement.</p>
                <div className="contact-block"><span className="clabel">Email</span><span className="cvalue">security@jotunn.io</span></div>
                <div className="contact-block"><span className="clabel">PGP Available</span><span className="cvalue">For sensitive communications</span></div>
                <div className="contact-block"><span className="clabel">Location</span><span className="cvalue">Florida, United States</span></div>
                <div className="contact-block"><span className="clabel">Response Time</span><span className="cvalue">&lt; 24 business hours</span></div>
              </div>
              <div className="contact-form reveal">
                <div className="form-row">
                  <div className="form-group"><label className="jotunn-label">Full Name</label><input className="jotunn-input" type="text" placeholder="Your name"/></div>
                  <div className="form-group"><label className="jotunn-label">Company</label><input className="jotunn-input" type="text" placeholder="Organization"/></div>
                </div>
                <div className="form-group"><label className="jotunn-label">Corporate Email</label><input className="jotunn-input" type="email" placeholder="you@company.com"/></div>
                <div className="form-group">
                  <label className="jotunn-label">Service</label>
                  <select className="jotunn-select">
                    <option value="">Select a service</option>
                    <option>Penetration Testing</option>
                    <option>Vulnerability Assessment</option>
                    <option>Secure Code Review</option>
                    <option>Red Team Operation</option>
                    <option>Private Bug Bounty Program</option>
                    <option>Compliance Consulting</option>
                  </select>
                </div>
                <div className="form-group"><label className="jotunn-label">Project Description</label><textarea className="jotunn-textarea" placeholder="Describe your infrastructure, security needs, and estimated timeline..."/></div>
                <button className="form-btn" onClick={() => setFormSent(true)}>Send Request →</button>
                {formSent && <div className="form-success">// Message received. We will be in touch shortly.</div>}
              </div>
            </div>
          </div>
        </section>

        <footer className="jotunn-footer">
          <span className="foot-copy">© 2025 Jötunn Cybersecurity — All rights reserved</span>
          <ul className="foot-links">
            <li><a href="#">Privacy Policy</a></li>
            <li><a href="#">Terms of Service</a></li>
            <li><a href="#">Responsible Disclosure</a></li>
          </ul>
        </footer>

      </div>
    </div>
  );
}
