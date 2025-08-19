// PDF.js settings
pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/2.16.105/pdf.worker.min.js';

// Elements
const pdfViewer = document.getElementById('pdfViewer');
const progressBar = document.getElementById('progressBar');
const progressText = document.getElementById('progressText');
const currentPageEl = document.getElementById('currentPage');
const totalPagesEl = document.getElementById('totalPages');
const prevButton = document.getElementById('prevPage');
const nextButton = document.getElementById('nextPage');
const resetButton = document.getElementById('resetProgress');
const jumpButton = document.getElementById('jumpToMax');

// PDF document and state variables
let pdfDoc = null;
let currentPage = 1;
let totalPages = 0;
let pdfFilename = ''; // Will be set from URL query param
let studentName = null; // Will be fetched from session
let maxProgressPercent = 0; // Max percentage read
let currentZoomLevel = 1.0; // Default zoom level

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
        alert("Student name is required to view and track PDF progress.");
        // Disable UI or redirect
        pdfViewer.innerHTML = '<p style="color:red; text-align:center;">Cannot load PDF without student name.</p>';
        throw new Error("Student name not provided.");
    }
    return studentName;
}

// --- Functions ---

function showInitialPdfMessage(message = 'Loading PDF details...') {
    pdfViewer.innerHTML = `
        <div style="text-align:center; padding:40px 20px;">
            <h3>${message}</h3>
        </div>
    `;
    totalPagesEl.textContent = '0';
    currentPageEl.textContent = '0';
    progressBar.value = 0;
    progressText.textContent = '0.0';
    updateProgressTextColor(0);
}

async function loadPdfAndProgress() {
    pdfFilename = getQueryParam('pdf');
    if (!pdfFilename) {
        showInitialPdfMessage('No PDF specified in URL.');
        return;
    }

    try {
        await getStudentName(); // Ensures studentName is available
    } catch (e) {
        return; // Stop if student name couldn't be obtained
    }

    showInitialPdfMessage(`Loading ${pdfFilename}...`);

    try {
        // Fetch initial progress from backend
        const progressRes = await fetch(`/api/progress_pdf/${studentName}/${encodeURIComponent(pdfFilename)}`, { credentials: 'include' });
        if (progressRes.ok) {
            const progressData = await progressRes.json();
            currentPage = progressData.currentPage || 1;
            maxProgressPercent = progressData.maxProgressPercent || 0;
        } else {
            console.warn("Could not load initial progress, starting from page 1.");
            currentPage = 1;
            maxProgressPercent = 0;
        }

        const pdfUrl = `/uploads_pdf/${encodeURIComponent(pdfFilename)}`;
        const loadingTask = pdfjsLib.getDocument(pdfUrl);
        pdfDoc = await loadingTask.promise;
        totalPages = pdfDoc.numPages;
        totalPagesEl.textContent = totalPages;

        if (currentPage < 1 || currentPage > totalPages) {
            currentPage = 1; // Reset to 1 if stored page is invalid
        }

        await renderPage(currentPage);
        // Initial progress display is handled by renderPage -> updateProgressAndSave

    } catch (error) {
        console.error('Error loading PDF or its progress:', error);
        showInitialPdfMessage(`Error loading ${pdfFilename}. Please check console.`);
    }
}

async function renderPage(pageNumber) {
    if (!pdfDoc) return;
    try {
        const page = await pdfDoc.getPage(pageNumber);
        
        // Get viewport dimensions
        const originalViewport = page.getViewport({ scale: 1.0 });
        
        // Calculate scale to fit the viewer width
        const viewerWidth = pdfViewer.clientWidth - 40; // subtract padding
        const baseScale = viewerWidth / originalViewport.width;
        
        // Apply the current zoom level
        const scale = baseScale * currentZoomLevel;
        
        // Create viewport with calculated scale
        const viewport = page.getViewport({ scale: scale });

        const canvas = document.createElement('canvas');
        const context = canvas.getContext('2d');
        canvas.height = viewport.height;
        canvas.width = viewport.width;

        pdfViewer.innerHTML = '';
        pdfViewer.appendChild(canvas);

        const renderContext = {
            canvasContext: context,
            viewport: viewport
        };
        
        // Update the zoom level display
        document.getElementById('zoomLevel').textContent = Math.round(currentZoomLevel * 100) + '%';

        await page.render(renderContext).promise;

        currentPageEl.textContent = pageNumber;
        await updateProgressAndSave(); // Update and save progress when page is rendered
    } catch (error) {
        console.error('Error rendering page:', error);
    }
}

async function updateProgressAndSave() {
    if (pdfDoc && totalPages > 0) {
        // Calculate progress based on the *start* of the current page.
        // If on page 1 of 10, 0% is completed. If on page 2, 10% is completed (1/10 pages).
        // If on the last page, it means (totalPages-1)/totalPages percent is completed.
        // When the user *finishes* the last page, we can mark it as 100%.
        let currentCompletionPercent = ((currentPage -1) / totalPages) * 100;
        if (currentPage === totalPages) { // If on the last page, consider it fully read for max progress purposes
            currentCompletionPercent = 100;
        }

        if (currentCompletionPercent > maxProgressPercent) {
            maxProgressPercent = currentCompletionPercent;
        }

        progressBar.value = maxProgressPercent;
        progressText.textContent = maxProgressPercent.toFixed(1);
        updateProgressTextColor(maxProgressPercent);

        // Save progress to backend
        if (studentName && pdfFilename) {
            try {
                await fetch(`/api/progress_pdf/${studentName}/${encodeURIComponent(pdfFilename)}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    credentials: 'include',
                    body: JSON.stringify({ currentPage: currentPage, maxProgressPercent: maxProgressPercent })
                });
            } catch (error) {
                console.error("Error saving PDF progress:", error);
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
        renderPage(currentPage);
    }
});

document.getElementById('zoomOut').addEventListener('click', () => {
    if (currentZoomLevel > 0.5) {
        currentZoomLevel -= 0.1;
        renderPage(currentPage);
    }
});

document.getElementById('fitWidth').addEventListener('click', () => {
    currentZoomLevel = 1.0; // Reset to default scale which is fit-to-width
    renderPage(currentPage);
});

prevButton.addEventListener('click', () => {
    if (currentPage > 1) {
        currentPage--;
        renderPage(currentPage);
    }
});

nextButton.addEventListener('click', () => {
    if (currentPage < totalPages) {
        currentPage++;
        renderPage(currentPage);
    }
});

resetButton.addEventListener('click', async () => {
    if (!pdfDoc || !studentName || !pdfFilename) {
        alert("No PDF loaded or student information missing.");
        return;
    }
    if (confirm('Are you sure you want to reset your reading progress for this PDF?')) {
        currentPage = 1;
        maxProgressPercent = 0;
        await renderPage(currentPage); // This will call updateProgressAndSave
        alert('Progress has been reset!');
    }
});

jumpButton.addEventListener('click', () => {
    if (!pdfDoc || totalPages === 0) {
        alert('Please load a PDF document first.');
        return;
    }

    // Calculate the page to jump to based on maxProgressPercent
    // If maxProgressPercent is 0, jump to page 1.
    // If maxProgressPercent is > 0, it means at least (maxProgressPercent/100 * totalPages) pages were started.
    // So we jump to floor(maxProgressPercent/100 * totalPages) + 1
    let pageToJump;
    if (maxProgressPercent === 0) {
        pageToJump = 1;
    } else if (maxProgressPercent === 100) {
        pageToJump = totalPages;
    } else {
        // This logic aims to get to the page *where* the max progress was achieved.
        // If maxProgressPercent is for *completed* pages, then the next page is where to continue.
        pageToJump = Math.floor((maxProgressPercent / 100) * totalPages) + 1;
    }
    
    pageToJump = Math.max(1, Math.min(pageToJump, totalPages)); // Clamp within bounds

    if (currentPage === pageToJump) {
        alert('You are already at your furthest read page, or the beginning.');
    } else {
        currentPage = pageToJump;
        renderPage(currentPage);
    }
});

// --- Initialization ---
async function initializeApp() {
    await loadPdfAndProgress();
    // Add beforeunload listener to ensure final progress is saved
    window.addEventListener('beforeunload', () => {
        // updateProgressAndSave will be called by renderPage, 
        // but an explicit save here might be good if user navigates away without page change
        if (pdfDoc && studentName && pdfFilename) {
             fetch(`/api/progress_pdf/${studentName}/${encodeURIComponent(pdfFilename)}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
                body: JSON.stringify({ currentPage: currentPage, maxProgressPercent: maxProgressPercent }),
                keepalive: true // Important for beforeunload
            }).catch(err => console.error("Error in final save on beforeunload:", err));
        }
    });
}

// Initialize PDF viewer on page load
initializeApp();