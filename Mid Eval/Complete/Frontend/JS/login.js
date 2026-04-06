// login.js

document.addEventListener('DOMContentLoaded', () => {
    const video = document.getElementById('webcam');
    const canvas = document.getElementById('snapshot');
    const capturedFrame = document.getElementById('captured-frame'); // NEW
    const scanBtn = document.getElementById('scan-btn');
    const btnText = document.getElementById('btn-text');
    const statusText = document.getElementById('system-status-text');
    const flashOverlay = document.getElementById('flash-overlay');
    const context = canvas.getContext('2d');

    // 1. Initialize the Webcam on page load
    navigator.mediaDevices.getUserMedia({ video: { facingMode: "user" } })
        .then((stream) => {
            video.srcObject = stream;
        })
        .catch((err) => {
            console.error("Camera access denied or hardware missing:", err);
            statusText.innerText = "ERROR: CAMERA HARDWARE NOT DETECTED";
            statusText.classList.replace("text-on-surface", "text-red-500");
        });

    // 2. Handle the Scan Button Click
    scanBtn.addEventListener('click', () => {
        if (scanBtn.disabled) return;
        
        // --- Visual Feedback ---
        scanBtn.disabled = true;
        btnText.innerText = "EXTRACTING BIOMETRICS...";
        statusText.innerText = "TRANSMITTING TO AUTH SERVER...";
        
        // Camera flash effect
        flashOverlay.classList.add('flash-effect');
        setTimeout(() => flashOverlay.classList.remove('flash-effect'), 400);

        // --- Core Logic: Capture Frame ---
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        
        context.translate(canvas.width, 0);
        context.scale(-1, 1);
        context.drawImage(video, 0, 0, canvas.width, canvas.height);
        
        const base64Image = canvas.toDataURL('image/jpeg', 0.9);
        
        // --- NEW: FREEZE THE FRAME ON SCREEN ---
        capturedFrame.src = base64Image;           // Paste the snapshot into the img tag
        video.classList.add('hidden');             // Hide the live moving video
        capturedFrame.classList.remove('hidden');  // Show the frozen picture
        
        console.log("✅ FRAME CAPTURED. Transmitting to backend...");

        // --- Hand off to Member 3's backend ---
        // Note: Using port 5001 to match your Lobby JS configuration
        fetch('http://localhost:5001/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ image: base64Image }),
            credentials: 'include' // Keep session cookies if backend uses them
        })
        .then(response => response.json())
        .then(data => {
            if(data.success) {
                btnText.innerText = "ACCESS GRANTED";
                statusText.innerText = `WELCOME, ${data.name.toUpperCase()}`;
                statusText.classList.replace("text-on-surface", "text-secondary");
                
                // Save user details to sessionStorage so Lobby can use them
                sessionStorage.setItem("arena_auth_user", data.name);
                sessionStorage.setItem("arena_auth_uid", data.uid);
                sessionStorage.setItem("arena_auth_elo", data.elo_rating);
                
                setTimeout(() => {
                    window.location.href = "lobby_command_center.html"; 
                }, 1500);
            } else {
                throw new Error("Face not recognized in database.");
            }
        })
        .catch(error => {
            console.error("Auth server offline or face mismatched.", error);
            
            btnText.innerText = "AUTH SERVER OFFLINE / FAILED";
            statusText.innerText = "CONNECTION REFUSED. RETRY?";
            statusText.classList.replace("text-on-surface", "text-[#ffb4ab]"); 
            
            setTimeout(() => {
                // Reset UI
                btnText.innerText = "SCAN IDENTITY";
                statusText.innerText = "SYSTEM READY: AWAITING INPUT";
                statusText.classList.replace("text-[#ffb4ab]", "text-on-surface");
                scanBtn.disabled = false;
                
                // --- NEW: UNFREEZE THE FRAME (BACK TO LIVE VIDEO) ---
                capturedFrame.classList.add('hidden');  // Hide the frozen picture
                video.classList.remove('hidden');       // Show the live video again
                
            }, 2500); // Waits 2.5 seconds before resetting so the user can read the error
        });
    });
});