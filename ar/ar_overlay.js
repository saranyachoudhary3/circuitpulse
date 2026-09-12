class AROverlayManager {
    constructor(canvasId, videoId) {
        this.canvas = document.getElementById(canvasId);
        this.ctx = this.canvas.getContext('2d');
        this.video = document.getElementById(videoId);
        this.detections = [];
        this.report = {};
        this.pulseAngle = 0;

        window.addEventListener('resize', () => this.resizeCanvas());
        this.resizeCanvas();
        this.animate();
    }

    resizeCanvas() {
        if (!this.canvas || !this.video) return;
        this.canvas.width = this.video.clientWidth || window.innerWidth;
        this.canvas.height = this.video.clientHeight || window.innerHeight;
    }

    updateData(detections, report) {
        this.detections = detections || [];
        this.report = report || {};
    }

    animate() {
        this.pulseAngle += 0.05;
        this.render();
        requestAnimationFrame(() => this.animate());
    }

    render() {
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);

        const videoW = 640;
        const videoH = 480;
        const scaleX = this.canvas.width / videoW;
        const scaleY = this.canvas.height / videoH;

        // Draw AR highlights for detected components
        for (const det of this.detections) {
            const bbox = det.bbox;
            const x1 = bbox.x1 * scaleX;
            const y1 = bbox.y1 * scaleY;
            const x2 = bbox.x2 * scaleX;
            const y2 = bbox.y2 * scaleY;
            const w = x2 - x1;
            const h = y2 - y1;

            if (det.class.toLowerCase() === 'resistor' && det.resistance) {
                this.drawResistorBadge(x1, y1, w, h, det);
            }
        }

        // Draw pin corrections if error reports a wrong pin
        const errors = this.report.errors || [];
        for (const err of errors) {
            if (err.type === 'wrong_pin') {
                this.drawWrongPinArrow(err, scaleX, scaleY);
            }
        }
    }

    drawResistorBadge(x, y, w, h, det) {
        const text = det.resistance;
        const bands = det.bands_str || '';
        const badgeH = 24;

        this.ctx.save();
        this.ctx.fillStyle = 'rgba(15, 23, 36, 0.85)';
        this.ctx.strokeStyle = '#00f2ff';
        this.ctx.lineWidth = 1.5;

        const badgeW = this.ctx.measureText(text + ' ' + bands).width + 24;
        const badgeX = x + (w - badgeW) / 2;
        const badgeY = Math.max(10, y - badgeH - 8);

        this.ctx.beginPath();
        this.ctx.roundRect(badgeX, badgeY, badgeW, badgeH, 4);
        this.ctx.fill();
        this.ctx.stroke();

        this.ctx.fillStyle = '#00f2ff';
        this.ctx.font = 'bold 12px monospace';
        this.ctx.fillText(text + (bands ? ' [' + bands + ']' : ''), badgeX + 8, badgeY + 16);
        this.ctx.restore();
    }

    drawWrongPinArrow(err, scaleX, scaleY) {
        // Render glowing target on target pin
        const pulse = 6 * Math.sin(this.pulseAngle);

        this.ctx.save();
        this.ctx.strokeStyle = '#38ef7d';
        this.ctx.fillStyle = 'rgba(56, 239, 125, 0.2)';
        this.ctx.lineWidth = 2;

        const targetX = 220 * scaleX;
        const targetY = 120 * scaleY;

        this.ctx.beginPath();
        this.ctx.arc(targetX, targetY, 14 + pulse, 0, Math.PI * 2);
        this.ctx.fill();
        this.ctx.stroke();

        this.ctx.fillStyle = '#38ef7d';
        this.ctx.font = 'bold 11px sans-serif';
        this.ctx.fillText(Target: Pin , targetX + 20, targetY + 4);
        this.ctx.restore();
    }
}

window.AROverlayManager = AROverlayManager;
