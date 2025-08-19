document.addEventListener('DOMContentLoaded', () => {
    // Elements
    const fileInput = document.getElementById('docx-file');
    const uploadBtn = document.getElementById('upload-btn');
    const docViewer = document.getElementById('document-viewer');
    const viewerContainer = document.getElementById('viewer-container');
    const progressBar = document.getElementById('progress-bar');
    const progressText = document.getElementById('progress-text');

    // Variables
    let maxScrollPercentage = 0;

    // Handle file upload
    uploadBtn.addEventListener('click', () => {
        if (fileInput.files.length === 0) {
            alert('Please select a DOCX file to upload');
            return;
        }

        const file = fileInput.files[0];
        if (file.type !== 'application/vnd.openxmlformats-officedocument.wordprocessingml.document') {
            alert('Please select a valid DOCX file');
            return;
        }

        // Show loading indicator
        docViewer.innerHTML = '<div class="loading">Loading document...</div>';
        viewerContainer.style.display = 'flex';

        // Reset progress
        maxScrollPercentage = 0;
        updateProgressBar(0);
        
        // Process the file
        processDocx(file);
    });

    // Process DOCX file and render it in continuous mode
    async function processDocx(file) {
        try {
            // Create an ArrayBuffer from the file
            const arrayBuffer = await file.arrayBuffer();
            
            // Clear the viewer
            docViewer.innerHTML = '';
            
            // Create a container for the DOCX preview
            const docxContainer = document.createElement('div');
            docxContainer.className = 'docx-container';
            docViewer.appendChild(docxContainer);
            
            // Render the DOCX using docx-preview in continuous mode
            await docx.renderAsync(arrayBuffer, docxContainer, null, {
                className: 'docx',
                inWrapper: true,
                ignoreHeight: false,
                ignoreWidth: false,
                renderHeaders: true,
                renderFooters: true,
                renderFootnotes: true,
                renderEndnotes: true
            });
            
            // Once loaded, setup scroll tracking
            setupScrollTracking();
            
        } catch (error) {
            console.error('Error processing DOCX file:', error);
            docViewer.innerHTML = `<div class="error">Error processing document: ${error.message}</div>`;
        }
    }

    // Setup scroll event tracking
    function setupScrollTracking() {
        // Reset progress on new document
        maxScrollPercentage = 0;
        updateProgressBar(0);
        
        // Add scroll event listener
        docViewer.addEventListener('scroll', handleScroll);
    }

    // Handle scroll events to update the progress bar
    function handleScroll() {
        const scrollPosition = docViewer.scrollTop;
        const scrollHeight = docViewer.scrollHeight - docViewer.clientHeight;
        
        // Calculate current scroll percentage
        const currentScrollPercentage = (scrollHeight > 0) 
            ? Math.round((scrollPosition / scrollHeight) * 100) 
            : 0;
        
        // Update max scroll percentage if current is higher
        if (currentScrollPercentage > maxScrollPercentage) {
            maxScrollPercentage = currentScrollPercentage;
            updateProgressBar(maxScrollPercentage);
        }
    }

    // Update the progress bar
    function updateProgressBar(percentage) {
        // Ensure percentage is between 0 and 100
        const validPercentage = Math.min(100, Math.max(0, percentage));
        
        // Update visual progress bar
        progressBar.style.width = `${validPercentage}%`;
        progressText.textContent = `${validPercentage}%`;
    }
}); 