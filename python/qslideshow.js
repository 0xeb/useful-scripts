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
        
        this.init();
    }
    
    async init() {
        await this.loadImages();
        await this.loadConfig();
        this.setupKeyboardShortcuts();
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