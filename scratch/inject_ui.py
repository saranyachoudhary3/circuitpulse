import os

html_path = r'c:\Users\Ayushman\Desktop\circuit_pulse\ar\index.html'

with open(html_path, 'r', encoding='utf-8') as f:
    html = f.read()

# Update the UI script in index.html to handle pending_steps and current_step
js_update = """
            if (rep.tutor_mode) {
                // Tutor Mode UI overrides
                banner.className = rep.status === 'PASS' && !rep.current_step ? 'ar-banner ok' : 'ar-banner warn';
                
                if (rep.current_step) {
                    bTitle.innerText = '[TUTORIAL] ' + rep.current_step.title;
                    bSol.innerText = '> ' + rep.current_step.desc;
                    bSol.style.display = 'block';
                    
                    let stepsHtml = `<div class="card warn-card">
                        <div class="card-title"> CURRENT: ${rep.current_step.title}</div>
                        <div class="card-desc">${rep.current_step.desc}</div>
                    </div>`;
                    
                    if (rep.pending_steps && rep.pending_steps.length > 0) {
                        stepsHtml += rep.pending_steps.map(s => 
                            `<div class="card" style="opacity: 0.5;">
                                <div class="card-title" style="color:#8b949e"> ${s.title}</div>
                            </div>`
                        ).join('');
                    }
                    errBox.innerHTML = stepsHtml;
                    
                    if (rep.tts) speakGuidance(rep.tts);
                    
                } else if (!rep.current_step && rep.status === 'PASS' && rep.circuit_id !== 'scanning') {
                    bTitle.innerText = '[OK] CIRCUIT VALIDATED';
                    bSol.innerText = 'Graph solver found 0 errors. Circuit is complete.';
                    bSol.style.display = 'block';
                    
                    errBox.innerHTML = `<div class="card ok-card">
                        <div class="card-title"> TUTORIAL COMPLETE</div>
                        <div class="card-desc">You have successfully built the circuit!</div>
                    </div>`;
                } else {
                     bTitle.innerText = 'SCANNING...';
                     bSol.style.display = 'none';
                     errBox.innerHTML = `<div class="card">
                        <div class="card-title" style="color:#8b949e">Waiting for components...</div>
                    </div>`;
                }
            } else {
                // Original logic (fallback)
"""

html = html.replace('if (rep.errors && rep.errors.length > 0) {', js_update + 'if (rep.errors && rep.errors.length > 0 && !rep.tutor_mode) {')
html = html.replace('} else if (rep.warnings && rep.warnings.length > 0) {', '} else if (rep.warnings && rep.warnings.length > 0 && !rep.tutor_mode) {')
html = html.replace('} else {', '} else if (!rep.tutor_mode) {')

with open(html_path, 'w', encoding='utf-8') as f:
    f.write(html)
