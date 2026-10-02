class OverlayManager {
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

    getColorForClass(className) {
        const cls = className.toLowerCase();
        if (cls.includes('arduino') || cls === 'mcu') return '#00ffcc';
        if (cls === 'breadboard') return 'rgba(255, 255, 255, 0.2)';
        if (cls === 'led') return '#ffcc00';
        if (cls === 'resistor') return '#00aaff';
        if (cls === 'wire') return '#ff00ff';
        return '#888888';
    }

    checkIfError(det) {
        if (this.report && this.report.vlm_analysis && this.report.vlm_analysis.status === 'HAS_ERRORS') {
            const errors = this.report.vlm_analysis.errors;
            if (errors && errors.length > 0) {
                const firstError = JSON.stringify(errors[0]).toLowerCase();
                const clsName = det.class.toLowerCase().replace('_', ' ');
                if (firstError.includes(clsName) || firstError.includes(det.class.toLowerCase())) {
                    return true;
                }
            }
        }
        return false;
    }

    render() {
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);

        // Dynamically get the intrinsic size of the MJPEG stream, fallback to 1920x1080
        const videoW = this.video.naturalWidth || 1920;
        const videoH = this.video.naturalHeight || 1080;
        const scaleX = this.canvas.width / videoW;
        const scaleY = this.canvas.height / videoH;

        for (const det of this.detections) {
            const bbox = det.bbox;
            const x1 = bbox.x1 * scaleX;
            const y1 = bbox.y1 * scaleY;
            const x2 = bbox.x2 * scaleX;
            const y2 = bbox.y2 * scaleY;
            const w = x2 - x1;
            const h = y2 - y1;

            const isError = this.checkIfError(det);
            const color = this.getColorForClass(det.class);

            this.drawBoundingBox(x1, y1, w, h, color, isError);
            this.drawLabel(x1, y1, det, color);

            if (det.class.toLowerCase() === 'resistor' && det.resistance) {
                this.drawResistorBadge(x1, y1, w, h, det);
            }
            
            if (det.class.toLowerCase() === 'wire' && det.endpoints) {
                this.drawWireEndpoints(det.endpoints, scaleX, scaleY);
            }
            
            if (det.class.toLowerCase() === 'breadboard') {
                this.drawBreadboardGrid(x1, y1, w, h);
            }
        }

        this.drawStatusIndicator();
    }

    drawBoundingBox(x, y, w, h, color, isError) {
        this.ctx.save();
        if (isError) {
            this.ctx.shadowColor = 'red';
            this.ctx.shadowBlur = 15;
            this.ctx.strokeStyle = 'red';
        } else {
            this.ctx.strokeStyle = color;
        }
        this.ctx.lineWidth = 2;
        
        const len = Math.min(15, w / 4, h / 4); // Length of corner lines

        this.ctx.beginPath();
        // Top-left
        this.ctx.moveTo(x, y + len);
        this.ctx.lineTo(x, y);
        this.ctx.lineTo(x + len, y);
        // Top-right
        this.ctx.moveTo(x + w - len, y);
        this.ctx.lineTo(x + w, y);
        this.ctx.lineTo(x + w, y + len);
        // Bottom-right
        this.ctx.moveTo(x + w, y + h - len);
        this.ctx.lineTo(x + w, y + h);
        this.ctx.lineTo(x + w - len, y + h);
        // Bottom-left
        this.ctx.moveTo(x + len, y + h);
        this.ctx.lineTo(x, y + h);
        this.ctx.lineTo(x, y + h - len);
        this.ctx.stroke();

        this.ctx.restore();
    }

    drawLabel(x, y, det, color) {
        this.ctx.save();
        const conf = ((det.confidence || 0) * 100).toFixed(0);
        const text = `${det.class} ${conf}%`;
        
        this.ctx.font = 'bold 11px monospace';
        const textWidth = this.ctx.measureText(text).width;
        
        const padX = 6;
        const rectW = textWidth + padX * 2;
        const rectH = 18;
        const rectX = x;
        const rectY = y - rectH - 4;

        this.ctx.fillStyle = 'rgba(0, 0, 0, 0.7)';
        this.ctx.beginPath();
        if (this.ctx.roundRect) {
            this.ctx.roundRect(rectX, rectY, rectW, rectH, 9); // Pill shape
        } else {
            this.ctx.rect(rectX, rectY, rectW, rectH);
        }
        this.ctx.fill();

        this.ctx.fillStyle = color === 'rgba(255, 255, 255, 0.2)' ? '#ffffff' : color;
        this.ctx.fillText(text, rectX + padX, rectY + 12);
        
        this.ctx.restore();
    }

    drawWireEndpoints(endpoints, scaleX, scaleY) {
        if (endpoints.length !== 2) return;
        const ep1 = endpoints[0];
        const ep2 = endpoints[1];
        
        const x1 = ep1[0] * scaleX;
        const y1 = ep1[1] * scaleY;
        const x2 = ep2[0] * scaleX;
        const y2 = ep2[1] * scaleY;
        
        this.ctx.save();
        this.ctx.strokeStyle = 'rgba(255, 0, 255, 0.8)';
        this.ctx.lineWidth = 2;
        this.ctx.setLineDash([5, 5]);
        this.ctx.beginPath();
        this.ctx.moveTo(x1, y1);
        this.ctx.lineTo(x2, y2);
        this.ctx.stroke();
        
        const pulse = 2 * Math.sin(this.pulseAngle);
        const radius = Math.max(0, 6 + pulse);
        
        this.ctx.fillStyle = '#ff00ff';
        this.ctx.beginPath();
        this.ctx.arc(x1, y1, radius, 0, Math.PI * 2);
        this.ctx.arc(x2, y2, radius, 0, Math.PI * 2);
        this.ctx.fill();
        this.ctx.restore();
    }

    drawBreadboardGrid(x, y, w, h) {
        this.ctx.save();
        this.ctx.strokeStyle = 'rgba(255, 255, 255, 0.2)';
        this.ctx.lineWidth = 1;
        
        this.ctx.beginPath();
        this.ctx.moveTo(x, y + h / 2);
        this.ctx.lineTo(x + w, y + h / 2);
        this.ctx.stroke();
        
        const isHorizontal = w > h;
        if (isHorizontal) {
            const step = w / 30;
            for (let i = 1; i < 30; i++) {
                this.ctx.beginPath();
                this.ctx.moveTo(x + i * step, y);
                this.ctx.lineTo(x + i * step, y + h);
                this.ctx.stroke();
            }
        }
        this.ctx.restore();
    }

    drawResistorBadge(x, y, w, h, det) {
        const text = det.resistance;
        const bands = det.bands_str || '';
        const badgeH = 20;

        this.ctx.save();
        this.ctx.fillStyle = 'rgba(20, 20, 20, 0.9)';
        this.ctx.strokeStyle = '#00aaff';
        this.ctx.lineWidth = 1;

        const badgeW = this.ctx.measureText(text + ' ' + bands).width + 16;
        const badgeX = x + (w - badgeW) / 2;
        const badgeY = Math.max(10, y + h + 4);

        this.ctx.beginPath();
        if (this.ctx.roundRect) {
            this.ctx.roundRect(badgeX, badgeY, badgeW, badgeH, 4);
        } else {
            this.ctx.rect(badgeX, badgeY, badgeW, badgeH);
        }
        this.ctx.fill();
        this.ctx.stroke();

        this.ctx.fillStyle = '#00aaff';
        this.ctx.font = 'bold 12px monospace';
        this.ctx.fillText(text + (bands ? ' [' + bands + ']' : ''), badgeX + 8, badgeY + 14);
        this.ctx.restore();
    }

    drawStatusIndicator() {
        let statusText = 'SCANNING';
        let color = '#ffcc00';
        let pulsing = false;

        if (this.report && this.report.vlm_analysis) {
            const vlmStatus = this.report.vlm_analysis.status;
            if (vlmStatus === 'HAS_ERRORS') {
                statusText = 'ERRORS';
                color = '#ff0000';
                pulsing = true;
            } else if (vlmStatus === 'WORKING') {
                statusText = 'VERIFIED';
                color = '#00ff00';
            }
        }

        this.ctx.save();
        
        this.ctx.font = 'bold 12px monospace';
        const textWidth = this.ctx.measureText(statusText).width;
        
        const badgeW = textWidth + 30; // space for dot
        const badgeH = 24;
        const badgeX = 10;
        const badgeY = 10;

        this.ctx.fillStyle = 'rgba(0, 0, 0, 0.7)';
        this.ctx.beginPath();
        if (this.ctx.roundRect) {
            this.ctx.roundRect(badgeX, badgeY, badgeW, badgeH, 4);
        } else {
            this.ctx.rect(badgeX, badgeY, badgeW, badgeH);
        }
        this.ctx.fill();

        // draw dot
        const dotX = badgeX + 12;
        const dotY = badgeY + 12;
        
        if (pulsing) {
            this.ctx.fillStyle = color;
            this.ctx.globalAlpha = 0.5 + 0.5 * Math.sin(this.pulseAngle * 2);
            this.ctx.beginPath();
            this.ctx.arc(dotX, dotY, 6, 0, Math.PI * 2);
            this.ctx.fill();
            this.ctx.globalAlpha = 1.0;
        }

        this.ctx.fillStyle = color;
        this.ctx.beginPath();
        this.ctx.arc(dotX, dotY, 4, 0, Math.PI * 2);
        this.ctx.fill();

        this.ctx.fillStyle = '#ffffff';
        this.ctx.fillText(statusText, dotX + 12, badgeY + 16);

        this.ctx.restore();
    }
}
window.OverlayManager = OverlayManager;
