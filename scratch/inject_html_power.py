import os

html_path = r'c:\Users\Ayushman\Desktop\circuit_pulse\ar\index.html'

with open(html_path, 'r', encoding='utf-8') as f:
    html = f.read()

old_logic = '''
            // Power Bank / Source Logic
            let hasMCU = dets.some(d => ['arduino_uno', 'arduino_nano', 'arduino_mega', 'esp32'].includes(d.class.toLowerCase()));
            const pbTag = document.getElementById('powerBankTag');
            if (hasMCU) {
                pbTag.innerText = ' POWER: USB/POWER-BANK ACTIVE';
                pbTag.style.color = '#00ffcc';
                pbTag.style.borderColor = '#00ffcc';
            } else {
                pbTag.innerText = ' POWER: UNKNOWN';
                pbTag.style.color = '#7d8590';
                pbTag.style.borderColor = '#30363d';
            }
'''

new_logic = '''
            // Active Visual Power Logic
            let hasMCU = dets.some(d => ['arduino_uno', 'arduino_nano', 'arduino_mega', 'esp32'].includes(d.class.toLowerCase()));
            const isPowered = rep.is_powered;
            const pbTag = document.getElementById('powerBankTag');
            
            if (hasMCU && isPowered) {
                pbTag.innerText = ' POWER: USB ACTIVE (BOARD LIT UP)';
                pbTag.style.color = '#00ffcc';
                pbTag.style.borderColor = '#00ffcc';
                pbTag.style.animation = 'none';
            } else if (hasMCU && !isPowered) {
                pbTag.innerText = ' POWER: BOARD OFF (PLUG IT IN)';
                pbTag.style.color = '#ff3366';
                pbTag.style.borderColor = '#ff3366';
                pbTag.style.animation = 'flash-fault 1s infinite alternate';
            } else {
                pbTag.innerText = ' POWER: UNKNOWN';
                pbTag.style.color = '#7d8590';
                pbTag.style.borderColor = '#30363d';
                pbTag.style.animation = 'none';
            }
'''

html = html.replace(old_logic.strip(), new_logic.strip())

with open(html_path, 'w', encoding='utf-8') as f:
    f.write(html)
