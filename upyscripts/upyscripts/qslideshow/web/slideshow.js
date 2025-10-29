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

        // Generate unique session ID for this tab/window
        this.sessionId = this.generateSessionId();
        console.log('Session ID:', this.sessionId);

        // Action system data
        this.hotkeys = {};
        this.gestures = {};
        this.actions = [];

        this.init();
    }

    generateSessionId() {
        // Use crypto.randomUUID() if available, otherwise fallback
        if (typeof crypto !== 'undefined' && crypto.randomUUID) {
            return crypto.randomUUID();
        }
        // Fallback for older browsers
        return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
            const r = Math.random() * 16 | 0;
            const v = c === 'x' ? r : (r & 0x3 | 0x8);
            return v.toString(16);
        });
    }

    getRequestOptions(options = {}) {
        // Add session ID header to all requests
        const headers = options.headers || {};
        headers['X-Session-ID'] = this.sessionId;
        return {
            ...options,
            credentials: 'include',
            headers: headers
        };
    }
    
    async init() {
        await this.loadImages();
        await this.loadConfig();
        await this.loadHotkeys();
        await this.loadGestures();
        await this.loadActions();
        this.setupKeyboardShortcuts();
        this.setupGestureHandlers();
        this.setupWakeLock();
        this.checkInstallPrompt();
        this.displayCurrentImage();
        this.startAutoAdvance();
        this.startStatusPolling();
    }
    
    async loadImages() {
        try {
            const response = await fetch('/api/images', this.getRequestOptions());
            const data = await response.json();
            this.images = data.images;
            console.log(`Loaded ${this.images.length} images`);
        } catch (error) {
            console.error('Failed to load images:', error);
        }
    }

    async loadConfig() {
        try {
            const response = await fetch('/api/config', this.getRequestOptions());
            this.config = await response.json();
            this.speedSeconds = this.config.speed || 3.0;
            this.repeat = this.config.repeat || false;
            this.shuffle = this.config.shuffle || false;
        } catch (error) {
            console.error('Failed to load config:', error);
        }
    }

    async loadHotkeys() {
        try {
            const response = await fetch('/api/hotkeys', this.getRequestOptions());
            const data = await response.json();
            this.hotkeys = data.hotkeys || {};
            console.log('Loaded hotkey mappings:', this.hotkeys);
        } catch (error) {
            console.error('Failed to load hotkeys:', error);
        }
    }

    async loadGestures() {
        try {
            const response = await fetch('/api/gestures', this.getRequestOptions());
            const data = await response.json();
            this.gestures = data.gestures || {};
            console.log('Loaded gesture mappings:', this.gestures);
        } catch (error) {
            console.error('Failed to load gestures:', error);
        }
    }
    
    async loadActions() {
        try {
            const response = await fetch('/api/actions', this.getRequestOptions());
            const data = await response.json();
            this.actions = data.actions || [];
            console.log(`Loaded ${this.actions.length} actions`);
        } catch (error) {
            console.error('Failed to load actions:', error);
        }
    }
    
    setupKeyboardShortcuts() {
        document.addEventListener('keydown', (e) => {
            // Don't handle shortcuts when help is visible
            const helpModal = document.getElementById('help-modal');
            const helpVisible = helpModal && helpModal.style.display === 'block';
            
            if (helpVisible && e.key !== 'Escape' && e.key !== 'h' && e.key !== 'H') {
                return;
            }
            
            // Build key string with modifiers
            let keyString = '';
            if (e.ctrlKey) keyString += 'ctrl+';
            if (e.altKey) keyString += 'alt+';
            if (e.shiftKey) keyString += 'shift+';
            if (e.metaKey) keyString += 'meta+';
            
            // Normalize key name
            let key = e.key;
            if (key === 'ArrowLeft') key = 'arrowleft';
            else if (key === 'ArrowRight') key = 'arrowright';
            else if (key === 'ArrowUp') key = 'arrowup';
            else if (key === 'ArrowDown') key = 'arrowdown';
            else if (key === ' ') key = 'space';
            else if (key === 'Enter') key = 'enter';
            else if (key === 'Escape') key = 'esc';
            else key = key.toLowerCase();
            
            keyString += key;
            
            // Check if this key is mapped to an action
            const action = this.hotkeys[keyString];
            if (action) {
                e.preventDefault();
                this.executeAction(action);
            }
        });
    }
    
    setupGestureHandlers() {
        let touchStartX = 0;
        let touchStartY = 0;
        let touchStartTime = 0;
        let touches = [];
        
        document.addEventListener('touchstart', (e) => {
            touchStartTime = Date.now();
            touches = Array.from(e.touches).map(t => ({
                x: t.clientX,
                y: t.clientY,
                id: t.identifier
            }));
            
            if (touches.length === 1) {
                touchStartX = touches[0].x;
                touchStartY = touches[0].y;
            }
            
            // Send to gesture detector
            this.sendGesture('touchstart', touches);
        });
        
        document.addEventListener('touchmove', (e) => {
            const currentTouches = Array.from(e.touches).map(t => ({
                x: t.clientX,
                y: t.clientY,
                id: t.identifier
            }));
            
            this.sendGesture('touchmove', currentTouches);
        });
        
        document.addEventListener('touchend', (e) => {
            const touchEndTime = Date.now();
            const duration = touchEndTime - touchStartTime;
            
            if (touches.length === 1 && e.touches.length === 0) {
                const deltaX = e.changedTouches[0].clientX - touchStartX;
                const deltaY = e.changedTouches[0].clientY - touchStartY;
                
                // Simple swipe detection (can be handled server-side too)
                if (Math.abs(deltaX) > 50 && Math.abs(deltaX) > Math.abs(deltaY)) {
                    if (deltaX > 0) {
                        this.handleGesture('swipe_right');
                    } else {
                        this.handleGesture('swipe_left');
                    }
                }
            }
            
            this.sendGesture('touchend', []);
        });
    }
    
    async sendGesture(eventType, touches) {
        try {
            const response = await fetch('/api/gesture', this.getRequestOptions({
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    event_type: eventType,
                    touches: touches
                })
            }));
            const result = await response.json();
            if (result.success) {
                this.handleActionResult(result);
            }
        } catch (error) {
            console.error('Failed to send gesture:', error);
        }
    }
    
    handleGesture(gestureName) {
        const action = this.gestures[gestureName];
        if (action) {
            this.executeAction(action);
        }
    }
    
    async executeAction(actionName, params = {}) {
        try {
            const response = await fetch('/api/execute', this.getRequestOptions({
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    action: actionName,
                    params: params
                })
            }));
            const result = await response.json();
            if (result.success) {
                this.handleActionResult(result);
            }
        } catch (error) {
            console.error(`Failed to execute action ${actionName}:`, error);
        }
    }
    
    handleActionResult(result) {
        // Update local state based on action result
        if ('current_index' in result) {
            this.currentIndex = result.current_index;
            this.displayCurrentImage();
            if (!this.isPaused) {
                this.resetTimer();
                this.startAutoAdvance();
            }
        }
        
        if ('is_paused' in result) {
            this.isPaused = result.is_paused;
            if (this.isPaused) {
                this.resetTimer();
            } else {
                this.startAutoAdvance();
            }
            this.updateStatus();
        }
        
        if ('repeat' in result) {
            this.repeat = result.repeat;
            console.log('Repeat:', this.repeat ? 'on' : 'off');
            this.updateStatus();
        }
        
        if ('shuffle' in result) {
            this.shuffle = result.shuffle;
            if ('current_index' in result) {
                this.currentIndex = result.current_index;
                this.displayCurrentImage();
            }
            console.log('Shuffle:', this.shuffle ? 'on' : 'off');
            this.updateStatus();
        }
        
        if ('speed' in result) {
            this.speedSeconds = result.speed;
            console.log(`Speed: ${this.speedSeconds}s`);
            this.updateStatus();
        }
        
        if ('is_fullscreen' in result && result.action === 'toggle_fullscreen') {
            this.toggleFullscreen();
        }
    }
    
    // Compatibility wrapper methods (can be removed later)
    nextImage() {
        this.executeAction('navigate_next');
    }
    
    previousImage() {
        this.executeAction('navigate_previous');
    }
    
    togglePause() {
        this.executeAction('toggle_pause');
    }
    
    toggleRepeat() {
        this.executeAction('toggle_repeat');
    }
    
    toggleShuffle() {
        this.executeAction('toggle_shuffle');
    }
    
    increaseSpeed() {
        this.executeAction('increase_speed');
    }
    
    decreaseSpeed() {
        this.executeAction('decrease_speed');
    }
    
    // Keep the original control method for backward compatibility
    async sendControl(action) {
        return await this.executeAction(action);
    }
    
    // UI-specific methods that don't go through actions
    toggleFullscreen() {
        if (!document.fullscreenElement) {
            document.documentElement.requestFullscreen().catch(err => {
                console.log('Error attempting to enable fullscreen:', err);
            });
        } else {
            if (document.exitFullscreen) {
                document.exitFullscreen();
            }
        }
    }
    
    togglePictureInPicture() {
        const img = document.getElementById('slideshow-image');
        if (!img) return;
        
        if (document.pictureInPictureElement) {
            document.exitPictureInPicture();
        } else if (document.pictureInPictureEnabled) {
            // Create a canvas to draw the image
            const canvas = document.createElement('canvas');
            const ctx = canvas.getContext('2d');
            canvas.width = img.naturalWidth;
            canvas.height = img.naturalHeight;
            ctx.drawImage(img, 0, 0);
            
            // Convert to video for PiP (images aren't directly supported)
            console.log('Picture-in-Picture for images requires special handling');
        }
    }
    
    toggleHelp() {
        const modal = document.getElementById('help-modal');
        if (modal) {
            if (modal.style.display === 'none' || !modal.style.display) {
                this.showHelp();
            } else {
                this.hideHelp();
            }
        }
    }
    
    showHelp() {
        const modal = document.getElementById('help-modal');
        if (modal) {
            // Build help content from loaded hotkeys
            const helpContent = this.buildHelpContent();
            const helpBody = modal.querySelector('.help-content');
            if (helpBody) {
                helpBody.innerHTML = helpContent;
            }
            modal.style.display = 'block';
        }
    }
    
    hideHelp() {
        const modal = document.getElementById('help-modal');
        if (modal) {
            modal.style.display = 'none';
        }
    }
    
    buildHelpContent() {
        let html = '<h3>Keyboard Shortcuts</h3><ul>';
        
        // Group actions by category
        const categories = {
            'Navigation': [],
            'Playback': [],
            'Display': [],
            'Speed': [],
            'Other': []
        };
        
        // Map actions to categories and find their hotkeys
        for (const [key, actionName] of Object.entries(this.hotkeys)) {
            const action = this.actions.find(a => a.name === actionName);
            if (action) {
                let category = 'Other';
                if (actionName.includes('navigate')) category = 'Navigation';
                else if (actionName.includes('pause') || actionName.includes('repeat') || actionName.includes('shuffle')) category = 'Playback';
                else if (actionName.includes('fullscreen') || actionName.includes('picture')) category = 'Display';
                else if (actionName.includes('speed')) category = 'Speed';
                
                categories[category].push({
                    key: key,
                    description: action.description
                });
            }
        }
        
        // Build HTML for each category
        for (const [category, items] of Object.entries(categories)) {
            if (items.length > 0) {
                html += `<li><strong>${category}:</strong><ul>`;
                for (const item of items) {
                    html += `<li>${item.key}: ${item.description}</li>`;
                }
                html += '</ul></li>';
            }
        }
        
        html += '</ul>';
        
        if (Object.keys(this.gestures).length > 0) {
            html += '<h3>Touch Gestures</h3><ul>';
            for (const [gesture, actionName] of Object.entries(this.gestures)) {
                const action = this.actions.find(a => a.name === actionName);
                if (action) {
                    html += `<li>${gesture.replace(/_/g, ' ')}: ${action.description}</li>`;
                }
            }
            html += '</ul>';
        }
        
        return html;
    }
    
    // Keep existing methods for wake lock, display, etc.
    setupWakeLock() {
        console.log('Setting up wake lock...');
        
        if ('wakeLock' in navigator) {
            console.log('Wake Lock API is available');
            this.requestWakeLock();
            
            this.wakeLockReacquireInterval = setInterval(() => {
                if (document.visibilityState === 'visible' && !this.wakeLock) {
                    console.log('Re-acquiring wake lock (periodic check)');
                    this.requestWakeLock();
                }
            }, 10000);
            
            document.addEventListener('visibilitychange', () => {
                console.log('Visibility changed to:', document.visibilityState);
                if (document.visibilityState === 'visible') {
                    this.requestWakeLock();
                } else if (document.visibilityState === 'hidden' && this.wakeLock) {
                    console.log('Page hidden, wake lock may be released by browser');
                }
            });
            
            window.addEventListener('focus', () => {
                console.log('Window focused, checking wake lock...');
                if (!this.wakeLock) {
                    this.requestWakeLock();
                }
            });
            
            window.addEventListener('pageshow', (event) => {
                console.log('Page show event, persisted:', event.persisted);
                this.requestWakeLock();
            });
        } else {
            console.log('Wake Lock API not supported, using fallback');
            this.setupNoSleepFallback();
        }
    }
    
    async requestWakeLock() {
        try {
            if (this.wakeLock && !this.wakeLock.released) {
                console.log('Wake lock already active');
                return;
            }
            
            this.wakeLock = await navigator.wakeLock.request('screen');
            console.log('Wake lock acquired successfully');
            
            this.wakeLock.addEventListener('release', () => {
                console.log('Wake lock was released');
                this.wakeLock = null;
            });
        } catch (err) {
            console.error(`Failed to acquire wake lock: ${err.name}, ${err.message}`);
        }
    }
    
    setupNoSleepFallback() {
        const video = document.createElement('video');
        video.setAttribute('muted', '');
        video.setAttribute('playsinline', '');
        video.style.position = 'absolute';
        video.style.top = '-100px';
        video.style.width = '1px';
        video.style.height = '1px';
        video.src = 'data:video/mp4;base64,AAAAIGZ0eXBpc29tAAACAGlzb21pc28yYXZjMW1wNDEAAAAIZnJlZQAAAs1tZGF0AAACrgYF//+q3EXpvebZSLeWLNgg2SPu73gyNjQgLSBjb3JlIDE0OCByMjYwMSBhMGNkN2QzIC0gSC4yNjQvTVBFRy00IEFWQyBjb2RlYyAtIENvcHlsZWZ0IDIwMDMtMjAxNSAtIGh0dHA6Ly93d3cudmlkZW9sYW4ub3JnL3gyNjQuaHRtbCAtIG9wdGlvbnM6IGNhYmFjPTEgcmVmPTMgZGVibG9jaz0xOjA6MCBhbmFseXNlPTB4MzoweDExMyBtZT1oZXggc3VibWU9NyBwc3k9MSBwc3lfcmQ9MS4wMDowLjAwIG1peGVkX3JlZj0xIG1lX3JhbmdlPTE2IGNocm9tYV9tZT0xIHRyZWxsaXM9MSA4eDhkY3Q9MSBjcW09MCBkZWFkem9uZT0yMSwxMSBmYXN0X3Bza2lwPTEgY2hyb21hX3FwX29mZnNldD0tMiB0aHJlYWRzPTEgbG9va2FoZWFkX3RocmVhZHM9MSBzbGljZWRfdGhyZWFkcz0wIG5yPTAgZGVjaW1hdGU9MSBpbnRlcmxhY2VkPTAgYmx1cmF5X2NvbXBhdD0wIGNvbnN0cmFpbmVkX2ludHJhPTAgYmZyYW1lcz0zIGJfcHlyYW1pZD0yIGJfYWRhcHQ9MSBiX2JpYXM9MCBkaXJlY3Q9MSB3ZWlnaHRiPTEgb3Blbl9nb3A9MCB3ZWlnaHRwPTIga2V5aW50PTI1MCBrZXlpbnRfbWluPTEwIHNjZW5lY3V0PTQwIGludHJhX3JlZnJlc2g9MCByY19sb29rYWhlYWQ9NDAgcmM9Y3JmIG1idHJlZT0xIGNyZj0yMy4wIHFjb21wPTAuNjAgcXBtaW49MCBxcG1heD02OSBxcHN0ZXA9NCBpcF9yYXRpbz0xLjQwIGFxPTE6MS4wMACAAAAAD2WIhAA3//728P4FNjuZQQAAAu5tb292AAAAbG12aGQAAAAAAAAAAAAAAAAAAAPoAAAAZAABAAABAAAAAAAAAAAAAAAAAQAAAAAAAAAAAAAAAAAAAAEAAAAAAAAAAAAAAAAAAEAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAACAAACGHRyYWsAAABcdGtoZAAAAAMAAAAAAAAAAAAAAAEAAAAAAAAAZAAAAAAAAAAAAAAAAAAAAAAAAQAAAAAAAAAAAAAAAAAAAAEAAAAAAAAAAAAAAAAAAEAAAAAAAgAAAAIAAAAAACRlZHRzAAAAHGVsc3QAAAAAAAAAAQAAAGQAAAAAAAEAAAAAAZBtZGlhAAAAIG1kaGQAAAAAAAAAAAAAAAAAACgAAAAEAFXEAAAAAAAtaGRscgAAAAAAAAAAdmlkZQAAAAAAAAAAAAAAAFZpZGVvSGFuZGxlcgAAAAE7bWluZgAAABR2bWhkAAAAAQAAAAAAAAAAAAAAJGRpbmYAAAAcZHJlZgAAAAAAAAABAAAADHVybCAAAAABAAAA+3N0YmwAAACXc3RzZAAAAAAAAAABAAAAh2F2YzEAAAAAAAAAAQAAAAAAAAAAAAAAAAAAAAAAAgACAEgAAABIAAAAAAAAAAEAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAY//8AAAAxYXZjQwFNQAr/4QAYZ01ACuiPyLZYAQAGaOvjyyLAAAAAHHV1aWRraEDyXyRPxbo5pRvPAyPzAAAAAAAAABhzdHRzAAAAAAAAAAEAAAABAAAABAAAABRzdHNzAAAAAAAAAAEAAAABAAAAFHN0c2MAAAAAAAAAAQAAAAEAAAABAAAAGHN0c3oAAAAAAAAAAAAAAAEAAAAVAAAAGHN0Y28AAAAAAAAAAQAAADAAAABidWR0YQAAAFptZXRhAAAAAAAAACFoZGxyAAAAAAAAAABtZGlyYXBwbAAAAAAAAAAAAAAAAC1pbHN0AAAAJal0b28AAAAdZGF0YQAAAAEAAAAATGF2ZjU2LjQwLjEwMQ==';
        document.body.appendChild(video);
        video.play();
    }
    
    displayCurrentImage() {
        if (this.images.length === 0) return;
        
        const img = document.getElementById('slideshow-image');
        if (!img) return;
        
        const imageData = this.images[this.currentIndex];
        img.src = `/api/image/${this.currentIndex}`;
        img.alt = imageData.name || `Image ${this.currentIndex + 1}`;
        
        this.updateStatus();
    }
    
    updateStatus() {
        const statusElement = document.getElementById('status-overlay');
        if (!statusElement) return;
        
        const current = this.currentIndex + 1;
        const total = this.images.length;
        const pauseStatus = this.isPaused ? ' (Paused)' : '';
        const repeatStatus = this.repeat ? ' 🔁' : '';
        const shuffleStatus = this.shuffle ? ' 🔀' : '';
        
        statusElement.textContent = `${current} / ${total}${pauseStatus}${repeatStatus}${shuffleStatus} | ${this.speedSeconds}s`;
    }
    
    resetTimer() {
        if (this.autoAdvanceTimer) {
            clearTimeout(this.autoAdvanceTimer);
            this.autoAdvanceTimer = null;
        }
    }
    
    startAutoAdvance() {
        this.resetTimer();
        if (!this.isPaused && this.images.length > 1) {
            this.autoAdvanceTimer = setTimeout(() => {
                this.autoAdvance();
            }, this.speedSeconds * 1000);
        }
    }
    
    autoAdvance() {
        this.executeAction('navigate_next');
    }
    
    async startStatusPolling() {
        setInterval(async () => {
            try {
                const response = await fetch('/api/status', this.getRequestOptions());
                const status = await response.json();
                
                if (status.current_index !== this.currentIndex) {
                    this.currentIndex = status.current_index;
                    this.displayCurrentImage();
                }
                
                this.isPaused = status.is_paused || false;
                this.repeat = status.repeat || false;
                this.shuffle = status.shuffle || false;
                this.speedSeconds = status.speed || 3.0;
                
                this.updateStatus();
            } catch (error) {
                // Status polling failed, ignore
            }
        }, 5000);
    }
    
    checkInstallPrompt() {
        if (this.isStandalone) {
            console.log('App is running in standalone mode');
        } else {
            const installPrompt = document.getElementById('install-prompt');
            if (installPrompt) {
                installPrompt.style.display = 'block';
                
                let deferredPrompt;
                window.addEventListener('beforeinstallprompt', (e) => {
                    e.preventDefault();
                    deferredPrompt = e;
                    
                    const installButton = document.getElementById('install-button');
                    if (installButton) {
                        installButton.addEventListener('click', () => {
                            deferredPrompt.prompt();
                            deferredPrompt.userChoice.then((choiceResult) => {
                                if (choiceResult.outcome === 'accepted') {
                                    console.log('User accepted the install prompt');
                                    installPrompt.style.display = 'none';
                                }
                                deferredPrompt = null;
                            });
                        });
                    }
                });
            }
        }
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    window.slideshow = new WebSlideshow();
});

// Helper functions for install prompt
function showInstallInstructions() {
    alert('To install this app:\n\n' +
          'Chrome/Edge: Click the menu (⋮) and select "Install app"\n' +
          'Safari: Tap Share button and select "Add to Home Screen"\n' +
          'Firefox: Open menu and select "Install"');
}

function dismissInstallPrompt() {
    const prompt = document.getElementById('install-prompt');
    if (prompt) {
        prompt.style.display = 'none';
    }
}