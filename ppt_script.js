// PPT Viewer Script - Image-based presentation viewer
// Elements
const pptViewer = document.getElementById('pptViewer');
const progressBar = document.getElementById('progressBar');
const progressText = document.getElementById('progressText');
const currentSlideEl = document.getElementById('currentSlide');
const totalSlidesEl = document.getElementById('totalSlides');
const prevButton = document.getElementById('prevSlide');
const nextButton = document.getElementById('nextSlide');
const resetButton = document.getElementById('resetProgress');
const jumpButton = document.getElementById('jumpToMax');

// PPT document and state variables
let currentSlide = 1;
let totalSlides = 0;
let pptFilename = ''; // Will be set from URL query param
let studentName = null; // Will be fetched from session
let maxProgressPercent = 0; // Max percentage viewed
let currentZoomLevel = 1.0; // Default zoom level
let slideImages = []; // Array to store slide image URLs

// --- Helper Functions ---
function getQueryParam(name) {
    const url = new URL(window.location.href);
    return url.searchParams.get(name);
}

async function getStudentName() {
    if (studentName) return studentName;
    try {
        const res = await fetch('/api/get_session_info', { credentials: 'include' });
        if (res.ok) {
            const data = await res.json();
            if (data.success && data.name) {
                studentName = data.name;
                return studentName;
            }
        }
    } catch (error) {
        console.error("Error fetching session info:", error);
    }
    // Fallback if session fetch fails or no name
    studentName = prompt('Enter your name to track progress:');
    if (!studentName) {
        alert("Student name is required to view and track PPT progress.");
        pptViewer.innerHTML = '<p style="color:red; text-align:center;">Cannot load PPT without student name.</p>';
        throw new Error("Student name not provided.");
    }
    return studentName;
}

// --- Functions ---

function showInitialPptMessage(message = 'Loading presentation...') {
    pptViewer.innerHTML = `
        <div style="text-align:center; padding:40px 20px;">
            <h3>${message}</h3>
        </div>
    `;
    totalSlidesEl.textContent = '0';
    currentSlideEl.textContent = '0';
    progressBar.value = 0;
    progressText.textContent = '0.0';
    updateProgressTextColor(0);
}

async function loadPptAndProgress() {
    pptFilename = getQueryParam('ppt');
    if (!pptFilename) {
        showInitialPptMessage('No presentation specified in URL.');
        return;
    }

    try {
        await getStudentName(); // Ensures studentName is available
    } catch (e) {
        return; // Stop if student name couldn't be obtained
    }

    showInitialPptMessage(`Loading ${pptFilename}...`);

    try {
        // Fetch initial progress from backend
        const progressRes = await fetch(`/api/progress_ppt/${studentName}/${encodeURIComponent(pptFilename)}`, { credentials: 'include' });
        if (progressRes.ok) {
            const progressData = await progressRes.json();
            currentSlide = progressData.currentSlide || 1;
            maxProgressPercent = progressData.maxProgressPercent || 0;
        } else {
            console.warn("Could not load initial progress, starting from slide 1.");
            currentSlide = 1;
            maxProgressPercent = 0;
        }

        // Get PPT info and load slides
        await loadPptSlides();

        if (currentSlide < 1 || currentSlide > totalSlides) {
            currentSlide = 1; // Reset to 1 if stored slide is invalid
        }

        await renderSlide(currentSlide);

    } catch (error) {
        console.error('Error loading PPT or its progress:', error);
        showInitialPptMessage(`Error loading ${pptFilename}. Please check console.`);
    }
}

async function loadPptSlides() {
    try {
        // Get PPT metadata from backend
        const response = await fetch(`/api/ppts`, { credentials: 'include' });
        
        if (response.ok) {
            const ppts = await response.json();
            const pptInfo = ppts.find(p => p.filename === pptFilename);
            
            if (pptInfo && pptInfo.slide_count) {
                totalSlides = pptInfo.slide_count;
                
                // Generate slide image URLs
                // Use the same logic as backend: remove extension properly
                const lastDotIndex = pptFilename.lastIndexOf('.');
                const filenameBase = lastDotIndex > 0 ? pptFilename.substring(0, lastDotIndex) : pptFilename;
                slideImages = [];
                for (let i = 1; i <= totalSlides; i++) {
                    const slideImageUrl = `/uploads_ppt_images/${encodeURIComponent(filenameBase)}/slide_${i.toString().padStart(3, '0')}.png`;
                    slideImages.push(slideImageUrl);
                }

                console.log(`Loaded PPT with ${totalSlides} slides`);
                console.log(`Filename base: "${filenameBase}"`);
                console.log(`First slide URL: "${slideImages[0]}"`);
            } else {
                throw new Error('PPT not found or no slide count available');
            }
        } else {
            throw new Error('Failed to fetch PPT info');
        }
        
        totalSlidesEl.textContent = totalSlides;
        
    } catch (error) {
        console.error('Error loading PPT slides:', error);
        throw error;
    }
}

async function renderSlide(slideNumber) {
    if (!slideImages || slideImages.length === 0) return;
    
    try {
        const slideImageUrl = slideImages[slideNumber - 1]; // Convert to 0-indexed
        
        // Create image element
        const img = document.createElement('img');
        img.style.maxWidth = '100%';
        img.style.height = 'auto';
        img.style.display = 'block';
        img.style.margin = '0 auto';
        img.style.transform = `scale(${currentZoomLevel})`;
        img.style.transformOrigin = 'center top';
        
        // Set up image load handler
        img.onload = () => {
            pptViewer.innerHTML = '';
            pptViewer.appendChild(img);
            
            // Update zoom level display
            document.getElementById('zoomLevel').textContent = Math.round(currentZoomLevel * 100) + '%';
            
            currentSlideEl.textContent = slideNumber;
            updateProgressAndSave(); // Update and save progress when slide is rendered
        };
        
        img.onerror = () => {
            pptViewer.innerHTML = `
                <div style="text-align:center; padding:40px 20px; color: red;">
                    <h3>Error loading slide ${slideNumber}</h3>
                    <p>Image not found: ${slideImageUrl}</p>
                </div>
            `;
        };
        
        img.src = slideImageUrl;
        
    } catch (error) {
        console.error('Error rendering slide:', error);
        pptViewer.innerHTML = `
            <div style="text-align:center; padding:40px 20px; color: red;">
                <h3>Error rendering slide ${slideNumber}</h3>
            </div>
        `;
    }
}

async function updateProgressAndSave() {
    if (totalSlides > 0) {
        // Calculate progress based on the current slide
        // Similar to PDF logic: if on slide 1 of 10, 0% completed. If on slide 2, 10% completed.
        let currentCompletionPercent = ((currentSlide - 1) / totalSlides) * 100;
        if (currentSlide === totalSlides) { // If on the last slide, consider it fully viewed
            currentCompletionPercent = 100;
        }

        if (currentCompletionPercent > maxProgressPercent) {
            maxProgressPercent = currentCompletionPercent;
        }

        progressBar.value = maxProgressPercent;
        progressText.textContent = maxProgressPercent.toFixed(1);
        updateProgressTextColor(maxProgressPercent);

        // Save progress to backend
        if (studentName && pptFilename) {
            try {
                await fetch(`/api/progress_ppt/${studentName}/${encodeURIComponent(pptFilename)}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    credentials: 'include',
                    body: JSON.stringify({ currentSlide: currentSlide, maxProgressPercent: maxProgressPercent })
                });
            } catch (error) {
                console.error("Error saving PPT progress:", error);
            }
        }
    } else {
        progressBar.value = 0;
        progressText.textContent = '0.0';
        updateProgressTextColor(0);
    }
}

function updateProgressTextColor(percentage) {
    if (percentage < 25) {
        progressText.style.color = '#f44336';
    } else if (percentage < 50) {
        progressText.style.color = '#ff9800';
    } else if (percentage < 75) {
        progressText.style.color = '#2196f3';
    } else {
        progressText.style.color = '#4caf50';
    }
}

// --- Event Listeners ---

// Zoom controls
document.getElementById('zoomIn').addEventListener('click', () => {
    if (currentZoomLevel < 2.0) {
        currentZoomLevel += 0.1;
        renderSlide(currentSlide);
    }
});

document.getElementById('zoomOut').addEventListener('click', () => {
    if (currentZoomLevel > 0.5) {
        currentZoomLevel -= 0.1;
        renderSlide(currentSlide);
    }
});

document.getElementById('fitWidth').addEventListener('click', () => {
    currentZoomLevel = 1.0; // Reset to default scale
    renderSlide(currentSlide);
});

prevButton.addEventListener('click', () => {
    if (currentSlide > 1) {
        currentSlide--;
        renderSlide(currentSlide);
    }
});

nextButton.addEventListener('click', () => {
    if (currentSlide < totalSlides) {
        currentSlide++;
        renderSlide(currentSlide);
    }
});

resetButton.addEventListener('click', async () => {
    if (!totalSlides || !studentName || !pptFilename) {
        alert("No presentation loaded or student information missing.");
        return;
    }
    if (confirm('Are you sure you want to reset your viewing progress for this presentation?')) {
        currentSlide = 1;
        maxProgressPercent = 0;
        await renderSlide(currentSlide); // This will call updateProgressAndSave
        alert('Progress has been reset!');
    }
});

jumpButton.addEventListener('click', () => {
    if (!totalSlides || totalSlides === 0) {
        alert('Please load a presentation first.');
        return;
    }

    // Calculate the slide to jump to based on maxProgressPercent
    let slideToJump;
    if (maxProgressPercent === 0) {
        slideToJump = 1;
    } else if (maxProgressPercent === 100) {
        slideToJump = totalSlides;
    } else {
        slideToJump = Math.floor((maxProgressPercent / 100) * totalSlides) + 1;
    }
    
    slideToJump = Math.max(1, Math.min(slideToJump, totalSlides)); // Clamp within bounds

    if (currentSlide === slideToJump) {
        alert('You are already at your furthest viewed slide, or the beginning.');
    } else {
        currentSlide = slideToJump;
        renderSlide(currentSlide);
    }
});

// --- Initialization ---
async function initializeApp() {
    await loadPptAndProgress();
    // Add beforeunload listener to ensure final progress is saved
    window.addEventListener('beforeunload', () => {
        if (totalSlides && studentName && pptFilename) {
             fetch(`/api/progress_ppt/${studentName}/${encodeURIComponent(pptFilename)}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
                body: JSON.stringify({ currentSlide: currentSlide, maxProgressPercent: maxProgressPercent }),
                keepalive: true // Important for beforeunload
            }).catch(err => console.error("Error in final save on beforeunload:", err));
        }
    });
}

// Initialize PPT viewer on page load
initializeApp();
