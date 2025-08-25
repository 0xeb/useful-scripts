class WebSlideshow {
    constructor() {
        this.currentIndex = 0;
        this.images = [];
        this.config = {};
        this.isPaused = false;
        this.autoAdvanceTimer = null;
        this.speedSeconds = 3.0;
        this.repeat = false;
        this.shuffle = false;
        this.wakeLock = null;
        this.isStandalone = window.matchMedia('(display-mode: standalone)').matches || 
                           window.navigator.standalone || 
                           document.referrer.includes('android-app://');
        
        this.init();
    }
    
    async init() {
        await this.loadImages();
        await this.loadConfig();
        this.setupKeyboardShortcuts();
        this.setupWakeLock();
        this.checkInstallPrompt();
        this.displayCurrentImage();
        this.startAutoAdvance();
        this.startStatusPolling();
    }
    
    async loadImages() {
        try {
            const response = await fetch('/api/images');
            const data = await response.json();
            this.images = data.images;
            console.log(`Loaded ${this.images.length} images`);
        } catch (error) {
            console.error('Failed to load images:', error);
        }
    }
    
    async loadConfig() {
        try {
            const response = await fetch('/api/config');
            this.config = await response.json();
            this.speedSeconds = this.config.speed || 3.0;
            this.repeat = this.config.repeat || false;
            this.shuffle = this.config.shuffle || false;
        } catch (error) {
            console.error('Failed to load config:', error);
        }
    }
    
    setupWakeLock() {
        // Check if Wake Lock API is available
        if ('wakeLock' in navigator) {
            // Request wake lock on initialization (regardless of pause state)
            this.requestWakeLock();
            
            // Re-acquire wake lock when page becomes visible
            document.addEventListener('visibilitychange', () => {
                if (document.visibilityState === 'visible') {
                    this.requestWakeLock();
                }
            });
        } else {
            console.log('Wake Lock API not supported');
            // Fallback: prevent sleep using hidden video trick for older browsers
            this.setupNoSleepFallback();
        }
    }
    
    async requestWakeLock() {
        if ('wakeLock' in navigator) {
            try {
                this.wakeLock = await navigator.wakeLock.request('screen');
                this.updateWakeLockStatus(true);
                console.log('Wake lock acquired');
                
                this.wakeLock.addEventListener('release', () => {
                    console.log('Wake lock released');
                    this.updateWakeLockStatus(false);
                });
            } catch (err) {
                console.error('Failed to acquire wake lock:', err);
            }
        }
    }
    
    async releaseWakeLock() {
        if (this.wakeLock) {
            try {
                await this.wakeLock.release();
                this.wakeLock = null;
                this.updateWakeLockStatus(false);
            } catch (err) {
                console.error('Failed to release wake lock:', err);
            }
        }
    }
    
    updateWakeLockStatus(active) {
        const statusEl = document.getElementById('wake-lock-status');
        if (statusEl) {
            statusEl.textContent = active ? '☀ Screen will stay on' : '';
        }
    }
    
    setupNoSleepFallback() {
        // Create a hidden video element that plays to prevent sleep
        const video = document.createElement('video');
        video.setAttribute('playsinline', '');
        video.setAttribute('muted', '');
        video.setAttribute('loop', '');
        video.style.position = 'absolute';
        video.style.width = '1px';
        video.style.height = '1px';
        video.style.left = '-100px';
        // Use a data URL for a tiny video
        video.src = 'data:video/mp4;base64,AAAAIGZ0eXBpc29tAAACAGlzb21pc28yYXZjMW1wNDEAAAAIZnJlZQAAAs1tZGF0AAACrgYF//+q3EXpvebZSLeWLNgg2SPu73gyNjQgLSBjb3JlIDE0OCByMjYwMSBhMGNkN2QzIC0gSC4yNjQvTVBFRy00IEFWQyBjb2RlYyAtIENvcHlsZWZ0IDIwMDMtMjAxNSAtIGh0dHA6Ly93d3cudmlkZW9sYW4ub3JnL3gyNjQuaHRtbCAtIG9wdGlvbnM6IGNhYmFjPTEgcmVmPTMgZGVibG9jaz0xOjA6MCBhbmFseXNlPTB4MzoweDExMyBtZT1oZXggc3VibWU9NyBwc3k9MSBwc3lfcmQ9MS4wMDowLjAwIG1peGVkX3JlZj0xIG1lX3JhbmdlPTE2IGNocm9tYV9tZT0xIHRyZWxsaXM9MSA4eDhkY3Q9MSBjcW09MCBkZWFkem9uZT0yMSwxMSBmYXN0X3Bza2lwPTEgY2hyb21hX3FwX29mZnNldD0tMiB0aHJlYWRzPTEgbG9va2FoZWFkX3RocmVhZHM9MSBzbGljZWRfdGhyZWFkcz0wIG5yPTAgZGVjaW1hdGU9MSBpbnRlcmxhY2VkPTAgYmx1cmF5X2NvbXBhdD0wIGNvbnN0cmFpbmVkX2ludHJhPTAgYmZyYW1lcz0zIGJfcHlyYW1pZD0yIGJfYWRhcHQ9MSBiX2JpYXM9MCBkaXJlY3Q9MSB3ZWlnaHRiPTEgb3Blbl9nb3A9MCB3ZWlnaHRwPTIga2V5aW50PTI1MCBrZXlpbnRfbWluPTEwIHNjZW5lY3V0PTQwIGludHJhX3JlZnJlc2g9MCByY19sb29rYWhlYWQ9NDAgcmM9Y3JmIG1idHJlZT0xIGNyZj0yMy4wIHFjb21wPTAuNjAgcXBtaW49MCBxcG1heD02OSBxcHN0ZXA9NCBpcF9yYXRpbz0xLjQwIGFxPTE6MS4wMACAAAAAD2WIhAA3//728P4FNjuZQQAAAu5tb292AAAAbG12aGQAAAAAAAAAAAAAAAAAAAPoAAAAZAABAAABAAAAAAAAAAAAAAAAAQAAAAAAAAAAAAAAAAAAAAEAAAAAAAAAAAAAAAAAAEAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAACAAACGHRyYWsAAABcdGtoZAAAAAMAAAAAAAAAAAAAAAEAAAAAAAAAZAAAAAAAAAAAAAAAAAAAAAAAAQAAAAAAAAAAAAAAAAAAAAEAAAAAAAAAAAAAAAAAAEAAAAAAAgAAAAIAAAAAACRlZHRzAAAAHGVsc3QAAAAAAAAAAQAAAGQAAAAAAAEAAAAAAZBtZGlhAAAAIG1kaGQAAAAAAAAAAAAAAAAAACgAAAAEAFXEAAAAAAAtaGRscgAAAAAAAAAAdmlkZQAAAAAAAAAAAAAAAFZpZGVvSGFuZGxlcgAAAAE7bWluZgAAABR2bWhkAAAAAQAAAAAAAAAAAAAAJGRpbmYAAAAcZHJlZgAAAAAAAAABAAAADHVybCAAAAABAAAA+3N0YmwAAACXc3RzZAAAAAAAAAABAAAAh2F2YzEAAAAAAAAAAQAAAAAAAAAAAAAAAAAAAAAAAgACAEgAAABIAAAAAAAAAAEAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAY//8AAAAxYXZjQwFkAAr/4QAYZ2QACqzZX4iIhAAAAwAEAAADAFA8SJZYAQAGaOvjyyLAAAAAGHN0dHMAAAAAAAAAAQAAAAEAAAQAAAAAHHN0c2MAAAAAAAAAAQAAAAEAAAABAAAAAQAAABRzdHN6AAAAAAAAAsUAAAABAAAAFHN0Y28AAAAAAAAAAQAAADAAAABidWR0YQAAAFptZXRhAAAAAAAAACFoZGxyAAAAAAAAAABtZGlyYXBwbAAAAAAAAAAAAAAAAC1pbHN0AAAAJal0b28AAAAdZGF0YQAAAAEAAAAATGF2ZjU2LjQwLjEwMQ==';
        document.body.appendChild(video);
        
        // Always play the video to keep screen awake (regardless of pause state)
        video.play().catch(() => {});
        
        this.noSleepVideo = video;
    }
    
    checkInstallPrompt() {
        // Check if running on iOS and not in standalone mode
        const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent);
        
        if (isIOS && !this.isStandalone && !localStorage.getItem('installPromptDismissed')) {
            setTimeout(() => {
                document.getElementById('install-prompt').style.display = 'block';
            }, 2000);
        }
    }
    
    setupKeyboardShortcuts() {
        document.addEventListener('keydown', (e) => {
            // Don't handle shortcuts when help is visible
            const helpModal = document.getElementById('help-modal');
            const helpVisible = helpModal.style.display === 'block';
            
            if (helpVisible && e.key !== 'Escape' && e.key !== 'h' && e.key !== 'H') {
                return;
            }
            
            switch(e.key) {
                case 'ArrowLeft': 
                    e.preventDefault();
                    this.previousImage(); 
                    break;
                case 'ArrowRight': 
                    e.preventDefault();
                    this.nextImage(); 
                    break;
                case ' ':
                case 'Enter': 
                    e.preventDefault();
                    this.togglePause(); 
                    break;
                case 'f':
                case 'F': 
                    this.toggleFullscreen(); 
                    break;
                case 'r':
                case 'R': 
                    this.toggleRepeat(); 
                    break;
                case 't':
                case 'T': 
                    this.togglePictureInPicture(); 
                    break;
                case 's':
                case 'S': 
                    this.toggleShuffle(); 
                    break;
                case '+':
                case '=': 
                    this.increaseSpeed(); 
                    break;
                case '-': 
                    this.decreaseSpeed(); 
                    break;
                case 'q':
                case 'Q':
                    if (helpVisible) {
                        this.hideHelp();
                    }
                    break;
                case 'Escape': 
                    if (helpVisible) {
                        this.hideHelp();
                    } else if (document.fullscreenElement) {
                        this.toggleFullscreen();
                    }
                    break;
                case 'h':
                case 'H': 
                    this.toggleHelp(); 
                    break;
            }
        });
    }
    
    async sendControl(action, params = {}) {
        try {
            const response = await fetch('/api/control', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ action, ...params })
            });
            return response.json();
        } catch (error) {
            console.error('Control request failed:', error);
        }
    }
    
    displayCurrentImage() {
        if (!this.images || this.images.length === 0) return;
        
        const img = document.getElementById('slideshow-image');
        img.src = `/api/image/${this.currentIndex}`;
        
        // Preload next image
        if (this.currentIndex < this.images.length - 1) {
            const nextImg = new Image();
            nextImg.src = `/api/image/${this.currentIndex + 1}`;
        }
        
        this.updateStatus();
    }
    
    async updateStatus() {
        try {
            const response = await fetch('/api/status');
            const status = await response.json();
            
            const overlay = document.getElementById('status-overlay');
            if (status.status_text) {
                overlay.textContent = status.status_text;
                overlay.style.display = 'block';
            } else {
                overlay.style.display = 'none';
            }
            
            // Update local state from server
            this.currentIndex = status.current_index || 0;
            this.isPaused = status.is_paused || false;
            this.speedSeconds = status.speed || 3.0;
            this.repeat = status.repeat || false;
            this.shuffle = status.shuffle || false;
        } catch (error) {
            console.error('Status update failed:', error);
        }
    }
    
    startStatusPolling() {
        setInterval(() => this.updateStatus(), 5000);
    }
    
    nextImage() {
        this.resetTimer();
        this.sendControl('next').then(result => {
            if (result && result.success) {
                this.currentIndex = result.current_index;
                this.displayCurrentImage();
                if (!this.isPaused) {
                    this.startAutoAdvance();
                }
            }
        });
    }
    
    previousImage() {
        this.resetTimer();
        this.sendControl('previous').then(result => {
            if (result && result.success) {
                this.currentIndex = result.current_index;
                this.displayCurrentImage();
                if (!this.isPaused) {
                    this.startAutoAdvance();
                }
            }
        });
    }
    
    togglePause() {
        this.sendControl('toggle_pause').then(result => {
            if (result && result.success) {
                this.isPaused = result.is_paused;
                if (this.isPaused) {
                    this.resetTimer();
                    // Keep wake lock active even when paused
                } else {
                    this.startAutoAdvance();
                }
                this.updateStatus();
            }
        });
    }
    
    toggleFullscreen() {
        if (!document.fullscreenElement) {
            document.documentElement.requestFullscreen().catch(err => {
                console.error('Fullscreen failed:', err);
            });
        } else {
            document.exitFullscreen();
        }
    }
    
    togglePictureInPicture() {
        const img = document.getElementById('slideshow-image');
        if (document.pictureInPictureElement) {
            document.exitPictureInPicture();
        } else if (document.pictureInPictureEnabled && img.tagName === 'VIDEO') {
            img.requestPictureInPicture().catch(err => {
                console.error('Picture-in-Picture not available for images');
            });
        } else {
            console.log('Picture-in-Picture not available for image elements');
        }
    }
    
    toggleRepeat() {
        this.sendControl('toggle_repeat').then(result => {
            if (result && result.success) {
                this.repeat = result.repeat;
                console.log('Repeat:', this.repeat ? 'on' : 'off');
                this.updateStatus();
            }
        });
    }
    
    toggleShuffle() {
        this.sendControl('toggle_shuffle').then(result => {
            if (result && result.success) {
                this.shuffle = result.shuffle;
                this.currentIndex = 0;
                this.displayCurrentImage();
                console.log('Shuffle:', this.shuffle ? 'on' : 'off');
                this.updateStatus();
            }
        });
    }
    
    increaseSpeed() {
        this.sendControl('increase_speed').then(result => {
            if (result && result.success) {
                this.speedSeconds = result.speed;
                console.log(`Speed: ${this.speedSeconds}s`);
                this.updateStatus();
            }
        });
    }
    
    decreaseSpeed() {
        this.sendControl('decrease_speed').then(result => {
            if (result && result.success) {
                this.speedSeconds = result.speed;
                console.log(`Speed: ${this.speedSeconds}s`);
                this.updateStatus();
            }
        });
    }
    
    toggleHelp() {
        const helpModal = document.getElementById('help-modal');
        if (helpModal.style.display === 'block') {
            this.hideHelp();
        } else {
            this.showHelp();
        }
    }
    
    showHelp() {
        document.getElementById('help-modal').style.display = 'block';
    }
    
    hideHelp() {
        document.getElementById('help-modal').style.display = 'none';
    }
    
    resetTimer() {
        if (this.autoAdvanceTimer) {
            clearTimeout(this.autoAdvanceTimer);
            this.autoAdvanceTimer = null;
        }
    }
    
    startAutoAdvance() {
        this.resetTimer();
        if (!this.isPaused && this.images && this.images.length > 0) {
            this.autoAdvanceTimer = setTimeout(() => {
                this.autoAdvance();
            }, this.speedSeconds * 1000);
        }
    }
    
    autoAdvance() {
        if (this.currentIndex >= this.images.length - 1 && !this.repeat) {
            return;
        }
        this.nextImage();
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    window.slideshow = new WebSlideshow();
});

// Helper functions for install prompt
function showInstallInstructions() {
    alert('To install:\n\n1. Tap the Share button (box with arrow)\n2. Scroll down and tap "Add to Home Screen"\n3. Tap "Add"\n\nThe app will then open in fullscreen without browser controls!');
}

function dismissInstallPrompt() {
    document.getElementById('install-prompt').style.display = 'none';
    localStorage.setItem('installPromptDismissed', 'true');
}