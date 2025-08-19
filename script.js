const video = document.getElementById('myVideo');
const progressBar = document.getElementById('progressBar');
const progressText = document.getElementById('progressText');

// Get video filename from query param
function getQueryParam(name) {
    const url = new URL(window.location.href);
    return url.searchParams.get(name);
}
const videoFilename = getQueryParam('video') || 'TP.mp4';

// Get student name from backend session (or prompt if not found)
let studentName = null;
async function getStudentName() {
    try {
        const res = await fetch('/api/get_session_info', {credentials: 'include'}); // Changed to GET and new endpoint
        if (res.ok) {
            const data = await res.json();
            if (data.success && data.name) {
                studentName = data.name;
            } else {
                studentName = prompt('Enter your name:');
            }
        } else {
            studentName = prompt('Enter your name:');
        }
    } catch {
        studentName = prompt('Enter your name:');
    }
}

let maxProgress = 0;

// --- Functions ---

// Update the progress bar and text display
function updateProgressDisplay() {
    if (video.duration) {
        const currentPercentage = (video.currentTime / video.duration) * 100;

        // Update maxProgress only if currentProgress is greater
        if (currentPercentage > maxProgress) {
            maxProgress = currentPercentage;
        }

        // Update the progress bar and text based on the persistent maxProgress
        progressBar.value = maxProgress;
        progressText.textContent = maxProgress.toFixed(1); // Show one decimal place
    } else {
        // Reset if duration isn't available (e.g., before video loads)
        progressBar.value = 0;
        progressText.textContent = '0.0';
    }
}

// Save the current time to Local Storage
async function saveProgress() {
    if (video.currentTime > 0 && video.duration) {
        // Only save if playback has started and is not at the very beginning/end
        if (video.currentTime < video.duration) {
            await fetch(`/api/progress/${studentName}/${videoFilename}`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                credentials: 'include',
                body: JSON.stringify({progress: maxProgress})
            });
        } else {
            // Optionally clear progress on finish
            await fetch(`/api/progress/${studentName}/${videoFilename}`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                credentials: 'include',
                body: JSON.stringify({progress: 100})
            });
        }
    }
}

// Load progress from Local Storage and set video time
async function loadProgress() {
    await getStudentName();
    try {
        const res = await fetch(`/api/progress/${studentName}/${videoFilename}`, {credentials: 'include'});
        const data = await res.json();
        maxProgress = data.progress || 0;
    } catch {
        maxProgress = 0;
    }
    updateProgressDisplay();
}

// --- Event Listeners ---

// 1. Load progress when the page is ready
loadProgress(); // This now also loads and sets maxProgress

// 2. Update display whenever the time updates
video.addEventListener('timeupdate', updateProgressDisplay); // This updates maxProgress if needed

// 3. Save progress when the user pauses the video
video.addEventListener('pause', saveProgress);

// 4. Save progress when the user leaves the page (important!)
window.addEventListener('beforeunload', saveProgress);

// 5. Clear progress if the video finishes playing
video.addEventListener('ended', async () => {
    maxProgress = 100;
    progressBar.value = 100;
    progressText.textContent = '100.0';
    await saveProgress();
});

// 6. Handle potential video loading errors
video.addEventListener('error', (e) => {
    console.error("Video Error:", e);
    // Potentially clear stored progress on error?
    // localStorage.removeItem(storageKeyTime);
    // localStorage.removeItem(storageKeyMaxProgress);
    alert("There was an error loading the video.");
});

// --- Add new interactive features ---

// Get the new buttons
const resetButton = document.getElementById('resetProgress');
const jumpButton = document.getElementById('jumpToMax');

// Reset progress button
resetButton.addEventListener('click', async () => {
    if (confirm('Are you sure you want to reset your watch progress?')) {
        maxProgress = 0;
        video.currentTime = 0;
        updateProgressDisplay();
        await fetch(`/api/progress/${studentName}/${videoFilename}`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            credentials: 'include',
            body: JSON.stringify({progress: 0})
        });
        alert('Progress has been reset!');
    }
});

// Jump to max progress button
jumpButton.addEventListener('click', () => {
    if (maxProgress > 0 && maxProgress < 100) {
        // Calculate time based on percentage
        const timeToJump = (maxProgress / 100) * video.duration;
        video.currentTime = timeToJump;
        video.play();
    } else {
        alert('No saved progress to continue from.');
    }
});

// Add visual feedback - change progress text color based on progress
video.addEventListener('timeupdate', () => {
    const progressText = document.getElementById('progressText');
    const percentage = (video.currentTime / video.duration) * 100;
    
    // Change color based on progress
    if (percentage < 25) {
        progressText.style.color = '#f44336'; // Red for early progress
    } else if (percentage < 50) {
        progressText.style.color = '#ff9800'; // Orange for moderate progress
    } else if (percentage < 75) {
        progressText.style.color = '#2196f3'; // Blue for good progress
    } else {
        progressText.style.color = '#4caf50'; // Green for nearly complete
    }
});
