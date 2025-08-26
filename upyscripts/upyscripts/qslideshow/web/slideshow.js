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
        this.wakeLockReacquireInterval = null;
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
        console.log('Setting up wake lock...');
        
        // Check if Wake Lock API is available
        if ('wakeLock' in navigator) {
            console.log('Wake Lock API is available');
            
            // Request wake lock on initialization (regardless of pause state)
            this.requestWakeLock();
            
            // Re-acquire wake lock periodically (every 10 seconds)
            this.wakeLockReacquireInterval = setInterval(() => {
                if (document.visibilityState === 'visible' && !this.wakeLock) {
                    console.log('Re-acquiring wake lock (periodic check)');
                    this.requestWakeLock();
                }
            }, 10000);
            
            // Re-acquire wake lock when page becomes visible
            document.addEventListener('visibilitychange', () => {
                console.log('Visibility changed to:', document.visibilityState);
                if (document.visibilityState === 'visible') {
                    this.requestWakeLock();
                } else if (document.visibilityState === 'hidden' && this.wakeLock) {
                    // Some browsers release wake lock when hidden, so we note this
                    console.log('Page hidden, wake lock may be released by browser');
                }
            });
            
            // Re-acquire wake lock on focus
            window.addEventListener('focus', () => {
                console.log('Window focused, checking wake lock...');
                if (!this.wakeLock) {
                    this.requestWakeLock();
                }
            });
            
            // Handle page show event (for when coming back from background)
            window.addEventListener('pageshow', (event) => {
                console.log('Page show event, persisted:', event.persisted);
                this.requestWakeLock();
            });
        } else {
            console.log('Wake Lock API not supported, using fallback');
            // Fallback: prevent sleep using hidden video trick for older browsers
            this.setupNoSleepFallback();
        }
        
        // Additional iOS-specific handling
        this.setupIOSWakeLock();
    }
    
    async requestWakeLock() {
        if ('wakeLock' in navigator) {
            try {
                // Release existing wake lock if any
                if (this.wakeLock) {
                    console.log('Releasing existing wake lock before re-acquiring');
                    try {
                        await this.wakeLock.release();
                    } catch (e) {
                        console.log('Error releasing existing wake lock:', e);
                    }
                    this.wakeLock = null;
                }
                
                this.wakeLock = await navigator.wakeLock.request('screen');
                this.updateWakeLockStatus(true);
                console.log('Wake lock acquired successfully at', new Date().toLocaleTimeString());
                
                this.wakeLock.addEventListener('release', () => {
                    console.log('Wake lock was released at', new Date().toLocaleTimeString());
                    this.wakeLock = null;
                    this.updateWakeLockStatus(false);
                    
                    // Try to re-acquire immediately if page is still visible
                    if (document.visibilityState === 'visible') {
                        console.log('Attempting to re-acquire wake lock after release...');
                        setTimeout(() => this.requestWakeLock(), 1000);
                    }
                });
            } catch (err) {
                console.error('Failed to acquire wake lock:', err.name, err.message);
                this.wakeLock = null;
                this.updateWakeLockStatus(false);
                
                // Retry after a delay if it's a temporary failure
                if (document.visibilityState === 'visible') {
                    console.log('Will retry wake lock in 5 seconds...');
                    setTimeout(() => this.requestWakeLock(), 5000);
                }
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
        console.log('Setting up NoSleep fallback video');
        
        // Create a hidden video element that plays to prevent sleep
        const video = document.createElement('video');
        video.setAttribute('playsinline', '');
        video.setAttribute('muted', '');
        video.setAttribute('loop', '');
        video.setAttribute('webkit-playsinline', 'true');
        video.style.position = 'absolute';
        video.style.width = '1px';
        video.style.height = '1px';
        video.style.left = '-100px';
        video.style.top = '-100px';
        // Use a data URL for a tiny video
        video.src = 'data:video/mp4;base64,AAAAIGZ0eXBpc29tAAACAGlzb21pc28yYXZjMW1wNDEAAAAIZnJlZQAAAs1tZGF0AAACrgYF//+q3EXpvebZSLeWLNgg2SPu73gyNjQgLSBjb3JlIDE0OCByMjYwMSBhMGNkN2QzIC0gSC4yNjQvTVBFRy00IEFWQyBjb2RlYyAtIENvcHlsZWZ0IDIwMDMtMjAxNSAtIGh0dHA6Ly93d3cudmlkZW9sYW4ub3JnL3gyNjQuaHRtbCAtIG9wdGlvbnM6IGNhYmFjPTEgcmVmPTMgZGVibG9jaz0xOjA6MCBhbmFseXNlPTB4MzoweDExMyBtZT1oZXggc3VibWU9NyBwc3k9MSBwc3lfcmQ9MS4wMDowLjAwIG1peGVkX3JlZj0xIG1lX3JhbmdlPTE2IGNocm9tYV9tZT0xIHRyZWxsaXM9MSA4eDhkY3Q9MSBjcW09MCBkZWFkem9uZT0yMSwxMSBmYXN0X3Bza2lwPTEgY2hyb21hX3FwX29mZnNldD0tMiB0aHJlYWRzPTEgbG9va2FoZWFkX3RocmVhZHM9MSBzbGljZWRfdGhyZWFkcz0wIG5yPTAgZGVjaW1hdGU9MSBpbnRlcmxhY2VkPTAgYmx1cmF5X2NvbXBhdD0wIGNvbnN0cmFpbmVkX2ludHJhPTAgYmZyYW1lcz0zIGJfcHlyYW1pZD0yIGJfYWRhcHQ9MSBiX2JpYXM9MCBkaXJlY3Q9MSB3ZWlnaHRiPTEgb3Blbl9nb3A9MCB3ZWlnaHRwPTIga2V5aW50PTI1MCBrZXlpbnRfbWluPTEwIHNjZW5lY3V0PTQwIGludHJhX3JlZnJlc2g9MCByY19sb29rYWhlYWQ9NDAgcmM9Y3JmIG1idHJlZT0xIGNyZj0yMy4wIHFjb21wPTAuNjAgcXBtaW49MCBxcG1heD02OSBxcHN0ZXA9NCBpcF9yYXRpbz0xLjQwIGFxPTE6MS4wMACAAAAAD2WIhAA3//728P4FNjuZQQAAAu5tb292AAAAbG12aGQAAAAAAAAAAAAAAAAAAAPoAAAAZAABAAABAAAAAAAAAAAAAAAAAQAAAAAAAAAAAAAAAAAAAAEAAAAAAAAAAAAAAAAAAEAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAACAAACGHRyYWsAAABcdGtoZAAAAAMAAAAAAAAAAAAAAAEAAAAAAAAAZAAAAAAAAAAAAAAAAAAAAAAAAQAAAAAAAAAAAAAAAAAAAAEAAAAAAAAAAAAAAAAAAEAAAAAAAgAAAAIAAAAAACRlZHRzAAAAHGVsc3QAAAAAAAAAAQAAAGQAAAAAAAEAAAAAAZBtZGlhAAAAIG1kaGQAAAAAAAAAAAAAAAAAACgAAAAEAFXEAAAAAAAtaGRscgAAAAAAAAAAdmlkZQAAAAAAAAAAAAAAAFZpZGVvSGFuZGxlcgAAAAE7bWluZgAAABR2bWhkAAAAAQAAAAAAAAAAAAAAJGRpbmYAAAAcZHJlZgAAAAAAAAABAAAADHVybCAAAAABAAAA+3N0YmwAAACXc3RzZAAAAAAAAAABAAAAh2F2YzEAAAAAAAAAAQAAAAAAAAAAAAAAAAAAAAAAAgACAEgAAABIAAAAAAAAAAEAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAY//8AAAAxYXZjQwFkAAr/4QAYZ2QACqzZX4iIhAAAAwAEAAADAFA8SJZYAQAGaOvjyyLAAAAAGHN0dHMAAAAAAAAAAQAAAAEAAAQAAAAAHHN0c2MAAAAAAAAAAQAAAAEAAAABAAAAAQAAABRzdHN6AAAAAAAAAsUAAAABAAAAFHN0Y28AAAAAAAAAAQAAADAAAABidWR0YQAAAFptZXRhAAAAAAAAACFoZGxyAAAAAAAAAABtZGlyYXBwbAAAAAAAAAAAAAAAAC1pbHN0AAAAJal0b28AAAAdZGF0YQAAAAEAAAAATGF2ZjU2LjQwLjEwMQ==';
        document.body.appendChild(video);
        
        // Function to ensure video keeps playing
        const ensureVideoPlaying = () => {
            if (video.paused) {
                video.play().catch((e) => {
                    console.log('NoSleep video play failed:', e);
                });
            }
        };
        
        // Always play the video to keep screen awake (regardless of pause state)
        video.play().catch((e) => {
            console.log('Initial NoSleep video play failed:', e);
        });
        
        // Ensure video stays playing
        setInterval(ensureVideoPlaying, 5000);
        
        // Re-play on visibility change
        document.addEventListener('visibilitychange', () => {
            if (document.visibilityState === 'visible') {
                ensureVideoPlaying();
            }
        });
        
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
    
    setupIOSWakeLock() {
        // iOS-specific handling
        const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent);
        
        if (isIOS) {
            console.log('iOS device detected, setting up iOS-specific wake lock handling');
            
            // Create an audio context for iOS
            const AudioContext = window.AudioContext || window.webkitAudioContext;
            if (AudioContext) {
                const audioContext = new AudioContext();
                
                // Create a silent audio loop
                const createSilentAudio = () => {
                    const source = audioContext.createBufferSource();
                    const buffer = audioContext.createBuffer(1, 1, 22050);
                    source.buffer = buffer;
                    source.connect(audioContext.destination);
                    source.loop = true;
                    source.start();
                    return source;
                };
                
                // Start on first user interaction
                const startAudio = () => {
                    if (audioContext.state === 'suspended') {
                        audioContext.resume().then(() => {
                            console.log('iOS AudioContext resumed');
                            createSilentAudio();
                        });
                    }
                };
                
                document.addEventListener('touchstart', startAudio, { once: true });
                document.addEventListener('click', startAudio, { once: true });
            }
            
            // Prevent iOS auto-lock by refreshing a hidden iframe periodically
            const iframe = document.createElement('iframe');
            iframe.style.display = 'none';
            document.body.appendChild(iframe);
            
            setInterval(() => {
                iframe.src = 'about:blank';
                setTimeout(() => {
                    iframe.src = '';
                }, 100);
            }, 20000); // Every 20 seconds
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