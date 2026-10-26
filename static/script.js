document.addEventListener('DOMContentLoaded', () => {
    // --- Global Auth & State ---
    let currentUser = null;
    const originalFetch = window.fetch;
    window.fetch = async function(url, options = {}) {
        if (typeof url === 'string') options.credentials = options.credentials || 'include';
        if (window.location.pathname === '/login') return await originalFetch.call(this, url, options);
        
        const response = await originalFetch.call(this, url, options);
        if (response.status === 401) {
            window.location.href = '/login';
        }
        return response;
    };

    // --- Theme Toggle ---
    const themeToggleBtn = document.getElementById('theme-toggle');
    const currentTheme = localStorage.getItem('theme');
    if (currentTheme === 'light') document.body.classList.add('light-theme');
    
    themeToggleBtn?.addEventListener('click', () => {
        document.body.classList.toggle('light-theme');
        const isLight = document.body.classList.contains('light-theme');
        localStorage.setItem('theme', isLight ? 'light' : 'dark');
        setTimeout(() => { if (document.getElementById('view-dashboard').classList.contains('active')) fetchWorkouts(); }, 10);
    });

    // --- View Navigation ---
    const views = {
        'nav-dashboard': 'view-dashboard',
        'nav-nutrition': 'view-nutrition',
        'nav-settings': 'view-settings'
    };
    
    function switchView(navId) {
        Object.keys(views).forEach(id => {
            const navEl = document.getElementById(id);
            const viewEl = document.getElementById(views[id]);
            if (navEl) navEl.classList.remove('active');
            if (viewEl) {
                viewEl.classList.remove('active');
                viewEl.classList.add('hidden');
            }
        });
        
        const activeNav = document.getElementById(navId);
        const activeView = document.getElementById(views[navId]);
        if (activeNav) activeNav.classList.add('active');
        if (activeView) {
            activeView.classList.remove('hidden');
            activeView.classList.add('active');
        }
        
        // Specific view triggers
        if (navId === 'view-dashboard') fetchWorkouts();
        if (navId === 'view-nutrition') fetchNutrition();
    }
    
    document.getElementById('nav-dashboard')?.addEventListener('click', () => switchView('nav-dashboard'));
    document.getElementById('nav-nutrition')?.addEventListener('click', () => switchView('nav-nutrition'));
    document.getElementById('nav-settings')?.addEventListener('click', () => switchView('nav-settings'));

    // --- Modals ---
    const historyModal = document.getElementById('history-modal');
    document.getElementById('nav-recent')?.addEventListener('click', async () => {
        const historyContent = document.getElementById('history-content');
        historyContent.innerHTML = 'Loading...';
        historyModal.classList.remove('hidden');
        
        try {
            const response = await fetch('/api/workouts');
            const data = await response.json();
            const workouts = data.workouts || data;
            if (workouts.length === 0) {
                historyContent.innerHTML = '<p>No history available.</p>';
                return;
            }
            workouts.sort((a, b) => new Date(b.date) - new Date(a.date));
            historyContent.innerHTML = workouts.map(w => {
                const d = new Date(w.date).toLocaleDateString();
                return `<div style="border-bottom: 1px solid var(--border-soft); padding: 8px 0; font-size: 14px;">
                    <b>${w.exercise_name}</b> - ${w.sets} sets x ${w.reps} reps @ ${w.weight_kg}kg <span style="color:var(--text-faint); float:right;">${d}</span>
                </div>`;
            }).join('');
        } catch(e) {
            historyContent.innerHTML = '<p>Error loading history.</p>';
        }
    });
    document.getElementById('history-close-btn')?.addEventListener('click', () => historyModal.classList.add('hidden'));
    historyModal?.addEventListener('click', (e) => { if(e.target === historyModal) historyModal.classList.add('hidden'); });

    // --- Settings & Auth Updates ---
    async function checkAuth() {
        try {
            const res = await fetch('/api/auth/me');
            if (res.ok) {
                currentUser = await res.json();
                updateUI();
                fetchWorkouts();
                fetchNutrition();
            } else {
                window.location.href = '/login';
            }
        } catch(e) { 
            window.location.href = '/login';
        }
    }
    
    function updateUI() {
        if (!currentUser) return;
        
        // Sidebar avatar
        const initials = (currentUser.username || currentUser.name || '?').substring(0,2).toUpperCase();
        const avatar = document.getElementById('nav-settings');
        if (avatar) avatar.textContent = initials;
        
        // Header (Dashboard)
        const headerGoalText = document.getElementById('header-goal-text');
        const headerSplitBtn = document.getElementById('header-split-btn');
        if (headerGoalText) headerGoalText.textContent = currentUser.goal || 'Recomp';
        if (headerSplitBtn) headerSplitBtn.textContent = currentUser.split || 'Custom';
        
        // Settings View
        const pUser = document.getElementById('profile-username');
        const pEmail = document.getElementById('profile-email');
        if (pUser) pUser.textContent = currentUser.username || currentUser.name || '';
        if (pEmail) pEmail.textContent = currentUser.email || '';
        
        const setWeight = document.getElementById('settings-weight');
        const setHeight = document.getElementById('settings-height');
        const setGoal = document.getElementById('settings-goal');
        const setSplit = document.getElementById('settings-split');
        if (setWeight) setWeight.value = currentUser.weight || '';
        if (setHeight) setHeight.value = currentUser.height || '';
        if (setGoal) setGoal.value = currentUser.goal || 'Recomp';
        if (setSplit) setSplit.value = currentUser.split || 'Push / Pull / Legs';

        // TOTP status
        if (currentUser.totp_enabled) {
            document.getElementById('totp-setup-section')?.style && (document.getElementById('totp-setup-section').style.display = 'none');
            const msg = document.getElementById('totp-enabled-msg');
            if (msg) msg.style.display = 'block';
        }
    }
    
    document.getElementById('settings-save-btn')?.addEventListener('click', async () => {
        const btn = document.getElementById('settings-save-btn');
        btn.textContent = 'Saving...';
        const weight = document.getElementById('settings-weight').value;
        const height = document.getElementById('settings-height').value;
        const goal = document.getElementById('settings-goal').value;
        const split = document.getElementById('settings-split').value;
        
        try {
            await fetch('/api/user/preferences', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ weight, height, goal, split })
            });
            currentUser.weight = weight;
            currentUser.height = height;
            currentUser.goal = goal;
            currentUser.split = split;
            updateUI();
            btn.textContent = 'Saved!';
            setTimeout(() => btn.textContent = 'Save Profile & Preferences', 2000);
        } catch(e) {
            btn.textContent = 'Error';
            setTimeout(() => btn.textContent = 'Save Profile & Preferences', 2000);
        }
    });

    // --- TOTP Enable Flow ---
    document.getElementById('totp-enable-btn')?.addEventListener('click', async () => {
        const btn = document.getElementById('totp-enable-btn');
        btn.textContent = 'Loading...';
        try {
            const res = await fetch('/api/auth/totp/setup', { method: 'POST', credentials: 'include' });
            const data = await res.json();
            if (!res.ok) { btn.textContent = 'Enable Two-Factor Auth'; alert(data.error || 'Failed to start setup.'); return; }
            // Show QR code
            const img = document.getElementById('totp-qr-img');
            if (img) img.src = `data:image/png;base64,${data.qr_code}`;
            document.getElementById('totp-qr-section').style.display = 'block';
            btn.style.display = 'none';
        } catch (e) {
            btn.textContent = 'Enable Two-Factor Auth';
        }
    });

    document.getElementById('totp-confirm-btn')?.addEventListener('click', async () => {
        const btn = document.getElementById('totp-confirm-btn');
        const code = document.getElementById('totp-confirm-code').value.trim();
        const errEl = document.getElementById('totp-setup-error');
        if (!code) { errEl.textContent = 'Please enter the code.'; errEl.style.display = 'block'; return; }
        btn.textContent = 'Confirming...';
        errEl.style.display = 'none';
        try {
            const res = await fetch('/api/auth/totp/enable', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                credentials: 'include',
                body: JSON.stringify({ code })
            });
            const data = await res.json();
            if (!res.ok) {
                errEl.textContent = data.error || 'Invalid code.';
                errEl.style.display = 'block';
                btn.textContent = 'Confirm & Enable';
            } else {
                // Success — update UI
                document.getElementById('totp-setup-section').style.display = 'none';
                const msg = document.getElementById('totp-enabled-msg');
                if (msg) msg.style.display = 'block';
                if (currentUser) currentUser.totp_enabled = true;
            }
        } catch (e) {
            errEl.textContent = 'Network error.';
            errEl.style.display = 'block';
            btn.textContent = 'Confirm & Enable';
        }
    });

    document.getElementById('btn-logout-modal')?.addEventListener('click', async () => {
        await originalFetch('/api/auth/logout', { method: 'POST' });
        window.location.href = '/login';
    });

    // AI Coach Recommendation
    document.getElementById('ai-recommend-btn')?.addEventListener('click', async () => {
        const btn = document.getElementById('ai-recommend-btn');
        const resDiv = document.getElementById('ai-recommend-result');
        btn.textContent = 'Analyzing...';
        
        try {
            const res = await fetch('/api/user/recommendation', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    weight: currentUser.weight,
                    height: currentUser.height,
                    goal: currentUser.goal,
                    split: currentUser.split
                })
            });
            const data = await res.json();
            resDiv.textContent = data.recommendation || data.error;
            resDiv.classList.remove('hidden');
        } catch (e) {
            resDiv.textContent = 'Error connecting to AI.';
            resDiv.classList.remove('hidden');
        } finally {
            btn.textContent = 'Get AI Coach Recommendation';
        }
    });

    // --- Dashboard: AI Log & Manual Form ---
    const aiForm = document.getElementById('ai-form');
    const workoutForm = document.getElementById('workout-form');
    const toggleManualBtn = document.getElementById('toggle-manual-btn');
    
    toggleManualBtn?.addEventListener('click', () => {
        const isAiHidden = aiForm.classList.contains('hidden');
        if (isAiHidden) {
            aiForm.classList.remove('hidden');
            workoutForm.classList.add('hidden');
            toggleManualBtn.textContent = 'Switch to Manual Entry';
        } else {
            aiForm.classList.add('hidden');
            workoutForm.classList.remove('hidden');
            toggleManualBtn.textContent = 'Switch to AI Entry';
            document.getElementById('date').valueAsDate = new Date();
        }
    });

    aiForm?.addEventListener('submit', async (e) => {
        e.preventDefault();
        const text = document.getElementById('ai_text').value;
        const spinner = document.getElementById('ai-spinner');
        const resDiv = document.getElementById('ai-result');
        const submitBtn = document.getElementById('ai-submit-btn');
        
        spinner.classList.remove('hidden');
        submitBtn.disabled = true;
        resDiv.classList.add('hidden');

        try {
            const response = await fetch('/api/workouts/ai', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text_input: text })
            });
            const data = await response.json();
            if (response.ok) {
                document.getElementById('ai_text').value = '';
                resDiv.textContent = 'Successfully logged.';
                resDiv.style.color = 'var(--text-mid)';
                fetchWorkouts();
            } else {
                resDiv.textContent = data.error || 'Failed to parse.';
                resDiv.style.color = 'var(--danger-color)';
            }
        } catch (error) {
            resDiv.textContent = 'Network error.';
            resDiv.style.color = 'var(--danger-color)';
        } finally {
            spinner.classList.add('hidden');
            submitBtn.disabled = false;
            resDiv.classList.remove('hidden');
            setTimeout(() => resDiv.classList.add('hidden'), 3000);
        }
    });

    workoutForm?.addEventListener('submit', async (e) => {
        e.preventDefault();
        const id = document.getElementById('edit_id').value;
        const payload = {
            exercise_name: document.getElementById('exercise_name').value,
            date: document.getElementById('date').value,
            sets: document.getElementById('sets').value,
            reps: document.getElementById('reps').value,
            weight_kg: document.getElementById('weight_kg').value
        };

        const method = id ? 'PUT' : 'POST';
        const url = id ? `/api/workouts/${id}` : '/api/workouts';

        const response = await fetch(url, {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (response.ok) {
            workoutForm.reset();
            document.getElementById('edit_id').value = '';
            document.getElementById('cancel-btn').classList.add('hidden');
            fetchWorkouts();
        }
    });

    document.getElementById('cancel-btn')?.addEventListener('click', () => {
        workoutForm.reset();
        document.getElementById('edit_id').value = '';
        document.getElementById('cancel-btn').classList.add('hidden');
    });

    // --- Dashboard: Data Fetch & Render ---
    async function fetchWorkouts() {
        try {
            const response = await fetch('/api/workouts');
            const data = await response.json();
            renderList(data.workouts || data);
            await fetchAnalytics();
        } catch (e) {
            console.error('Error fetching workouts', e);
        }
    }

    function renderList(workouts) {
        const list = document.getElementById('workout-list');
        const chipRow = document.getElementById('quick-repeat-chips');
        if (!list || !chipRow) return;

        list.innerHTML = '';
        chipRow.innerHTML = '';
        
        workouts.sort((a, b) => new Date(b.date) - new Date(a.date));

        const exerciseFreq = {};
        workouts.forEach(w => {
            exerciseFreq[w.exercise_name] = (exerciseFreq[w.exercise_name] || 0) + 1;
        });
        const topExercises = Object.entries(exerciseFreq)
            .sort((a, b) => b[1] - a[1])
            .slice(0, 3)
            .map(e => e[0]);

        topExercises.forEach(ex => {
            const btn = document.createElement('button');
            btn.className = 'chip';
            btn.textContent = '+ ' + ex;
            btn.onclick = () => {
                document.getElementById('ai_text').value = `3 sets of 10 ${ex}`;
                document.getElementById('ai_text').focus();
            };
            chipRow.appendChild(btn);
        });

        workouts.forEach(w => {
            const div = document.createElement('div');
            div.className = 'log-row';
            const d = new Date(w.date).toLocaleDateString();
            div.innerHTML = `
                <div class="log-details">
                    <div class="log-name">${w.exercise_name} <span>${d}</span></div>
                    <div class="log-meta">${w.sets} sets x ${w.reps} reps @ ${w.weight_kg}kg</div>
                </div>
                <div class="log-actions">
                    <button class="btn secondary-btn" onclick="editWorkout('${w._id}')">Edit</button>
                    <button class="btn secondary-btn" onclick="deleteWorkout('${w._id}')">Del</button>
                </div>
            `;
            list.appendChild(div);
        });
    }

    window.editWorkout = async function(id) {
        aiForm.classList.add('hidden');
        workoutForm.classList.remove('hidden');
        toggleManualBtn.textContent = 'Switch to AI Entry';

        const response = await fetch(`/api/workouts/${id}`);
        const workout = await response.json();
        document.getElementById('edit_id').value = workout._id;
        document.getElementById('exercise_name').value = workout.exercise_name;
        document.getElementById('date').value = workout.date.split('T')[0];
        document.getElementById('sets').value = workout.sets;
        document.getElementById('reps').value = workout.reps;
        document.getElementById('weight_kg').value = workout.weight_kg;
        document.getElementById('cancel-btn').classList.remove('hidden');
        workoutForm.scrollIntoView({ behavior: 'smooth', block: 'center' });
    };

    window.deleteWorkout = async function(id) {
        if (!confirm('Delete this workout?')) return;
        await fetch(`/api/workouts/${id}`, { method: 'DELETE' });
        fetchWorkouts();
    };

    // --- Dashboard: Analytics ---
    async function fetchAnalytics() {
        try {
            const response = await fetch('/api/analytics');
            const data = await response.json();
            renderAnalytics(data);
        } catch (e) { console.error('Error fetching analytics:', e); }
    }

    function renderAnalytics(data) {
        if (!data || !data.strength || !data.volume) return;
        
        const rootStyles = getComputedStyle(document.body);
        const textColor = rootStyles.getPropertyValue('--text').trim() || '#e9eaec';
        const gridColor = rootStyles.getPropertyValue('--border-soft').trim() || '#2b2f35';
        const cardBgColor = rootStyles.getPropertyValue('--bg').trim() || '#15171b';
        
        const strengthCtx = document.getElementById('oneRmChart');
        if (strengthCtx) {
            if (window.oneRmChartInstance) window.oneRmChartInstance.destroy();
            
            const colorPalette = ['#C79A3E', '#6B9C7C', '#B0623D', '#8A6E30', '#E9EAEC', '#9BA1A8'];
            data.strength.datasets.forEach((ds, idx) => {
                ds.borderColor = colorPalette[idx % colorPalette.length];
                ds.backgroundColor = colorPalette[idx % colorPalette.length];
                ds.tension = 0.3;
            });
            
            window.oneRmChartInstance = new Chart(strengthCtx.getContext('2d'), {
                type: 'line',
                data: {
                    labels: data.strength.labels,
                    datasets: data.strength.datasets
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { labels: { color: textColor } },
                        title: { display: true, text: 'Estimated 1RM Progression (kg)', color: textColor }
                    },
                    scales: {
                        x: { ticks: { color: textColor }, grid: { color: gridColor } },
                        y: { ticks: { color: textColor }, grid: { color: gridColor }, beginAtZero: false }
                    }
                }
            });
        }
        
        const volumeCtx = document.getElementById('volumePieChart');
        if (volumeCtx) {
            if (window.volumePieChartInstance) window.volumePieChartInstance.destroy();
            const colorPalette = ['#C79A3E', '#6B9C7C', '#B0623D', '#8A6E30', '#E9EAEC', '#9BA1A8'];
            
            window.volumePieChartInstance = new Chart(volumeCtx.getContext('2d'), {
                type: 'pie',
                data: {
                    labels: data.volume.labels,
                    datasets: [{
                        data: data.volume.data,
                        backgroundColor: colorPalette,
                        borderWidth: 2,
                        borderColor: cardBgColor
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { position: 'right', labels: { color: textColor } },
                        title: { display: true, text: 'Volume Distribution (Total Sets)', color: textColor }
                    }
                }
            });
        }
    }

    
    // --- Nutrition View ---
    async function fetchNutrition() {
        try {
            const res = await fetch('/api/meals/today');
            const data = await res.json();
            
            const mCal = document.getElementById('macro-calories');
            const mPro = document.getElementById('macro-protein');
            const mCarb = document.getElementById('macro-carbs');
            const mFat = document.getElementById('macro-fat');
            
            if (mCal) mCal.textContent = Math.round(data.calories);
            if (mPro) mPro.textContent = Math.round(data.protein) + 'g';
            if (mCarb) mCarb.textContent = Math.round(data.carbs) + 'g';
            if (mFat) mFat.textContent = Math.round(data.fat) + 'g';
        } catch (e) {
            console.error('Error fetching nutrition', e);
        }
    }

    // --- AI Coach Analytics ---
    document.getElementById('run-coach-btn')?.addEventListener('click', async () => {
        const btn = document.getElementById('run-coach-btn');
        const resDiv = document.getElementById('coach-result');
        btn.textContent = 'Analyzing...';
        resDiv.classList.add('hidden');
        
        try {
            const res = await fetch('/api/ai/coach-review');
            const data = await res.json();
            if (!res.ok) throw new Error(data.error || 'Failed to fetch insights');
            resDiv.innerHTML = (data.insights || 'No insights available').replace(/\n/g, '<br>');
            resDiv.classList.remove('hidden');
        } catch (e) {
            console.error(e);
            resDiv.textContent = 'Unable to generate insights right now.';
            resDiv.classList.remove('hidden');
        } finally {
            btn.textContent = 'Run 30-Day Analysis';
        }
    });

    // --- Camera & Crop Modal ---
    const mealUploadBox = document.getElementById('meal-upload-box');
    const mealCameraTrigger = document.getElementById('meal-camera-trigger');
    const mealFileInput = document.getElementById('meal-photo-input');
    const cameraModal = document.getElementById('camera-modal');
    
    const optContainer = document.getElementById('camera-options');
    const streamContainer = document.getElementById('camera-stream-container');
    const cropContainer = document.getElementById('crop-container');
    
    let liveStream = null;
    let baseImg = null;
    let imgScale = 1;
    let imgPanX = 0;
    let imgPanY = 0;
    
    function resetCameraModal() {
        if(liveStream) { liveStream.getTracks().forEach(t => t.stop()); liveStream = null; }
        optContainer.classList.remove('hidden');
        streamContainer.classList.add('hidden');
        cropContainer.classList.add('hidden');
        baseImg = null;
    }

    [mealUploadBox, mealCameraTrigger].forEach(el => {
        el?.addEventListener('click', () => {
            resetCameraModal();
            cameraModal.classList.remove('hidden');
        });
    });
    
    document.getElementById('camera-close-btn')?.addEventListener('click', () => {
        resetCameraModal();
        cameraModal.classList.add('hidden');
    });

    document.getElementById('btn-device-upload')?.addEventListener('click', () => {
        mealFileInput.click();
    });

    mealFileInput?.addEventListener('change', (e) => {
        const file = e.target.files[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onload = (ev) => {
            loadCropImage(ev.target.result);
        };
        reader.readAsDataURL(file);
    });

    document.getElementById('btn-live-photo')?.addEventListener('click', async () => {
        optContainer.classList.add('hidden');
        streamContainer.classList.remove('hidden');
        try {
            liveStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } });
            document.getElementById('live-video').srcObject = liveStream;
        } catch(e) {
            alert('Camera access denied or unavailable.');
            resetCameraModal();
        }
    });

    document.getElementById('btn-capture')?.addEventListener('click', () => {
        const video = document.getElementById('live-video');
        const snapCanvas = document.createElement('canvas');
        snapCanvas.width = video.videoWidth || 640;
        snapCanvas.height = video.videoHeight || 480;
        snapCanvas.getContext('2d').drawImage(video, 0, 0);
        
        if(liveStream) { liveStream.getTracks().forEach(t => t.stop()); liveStream = null; }
        loadCropImage(snapCanvas.toDataURL('image/jpeg'));
    });

    function loadCropImage(src) {
        optContainer.classList.add('hidden');
        streamContainer.classList.add('hidden');
        cropContainer.classList.remove('hidden');
        
        baseImg = new Image();
        baseImg.src = src;
        baseImg.onload = () => {
            const area = document.getElementById('crop-area');
            imgScale = Math.max(area.clientWidth / baseImg.width, area.clientHeight / baseImg.height);
            imgPanX = (area.clientWidth - baseImg.width * imgScale) / 2;
            imgPanY = (area.clientHeight - baseImg.height * imgScale) / 2;
            document.getElementById('crop-zoom').value = imgScale;
            drawCrop();
        };
    }

    const cropCanvas = document.getElementById('crop-canvas');
    const cropCtx = cropCanvas.getContext('2d');
    const cropArea = document.getElementById('crop-area');

    function drawCrop() {
        if (!baseImg) return;
        cropCanvas.width = cropArea.clientWidth;
        cropCanvas.height = cropArea.clientHeight;
        cropCtx.clearRect(0,0, cropCanvas.width, cropCanvas.height);
        cropCtx.drawImage(baseImg, imgPanX, imgPanY, baseImg.width * imgScale, baseImg.height * imgScale);
    }

    // Panning logic
    let isDown = false;
    let startX, startY;
    cropArea?.addEventListener('pointerdown', (e) => {
        isDown = true;
        startX = e.clientX - imgPanX;
        startY = e.clientY - imgPanY;
        cropArea.setPointerCapture(e.pointerId);
    });
    cropArea?.addEventListener('pointermove', (e) => {
        if(!isDown) return;
        imgPanX = e.clientX - startX;
        imgPanY = e.clientY - startY;
        drawCrop();
    });
    cropArea?.addEventListener('pointerup', () => isDown = false);
    
    // Zoom slider logic
    document.getElementById('crop-zoom')?.addEventListener('input', (e) => {
        if(!baseImg) return;
        const newScale = parseFloat(e.target.value);
        // keep centered
        const cx = cropArea.clientWidth / 2;
        const cy = cropArea.clientHeight / 2;
        imgPanX = cx - (cx - imgPanX) * (newScale / imgScale);
        imgPanY = cy - (cy - imgPanY) * (newScale / imgScale);
        imgScale = newScale;
        drawCrop();
    });

    document.getElementById('btn-confirm-crop')?.addEventListener('click', () => {
        const outCanvas = document.createElement('canvas');
        // crop box is 10% to 90%, so size is 80%
        const boxSize = cropArea.clientWidth * 0.8;
        const boxX = cropArea.clientWidth * 0.1;
        const boxY = cropArea.clientHeight * 0.1;
        
        outCanvas.width = boxSize;
        outCanvas.height = boxSize;
        const ctx = outCanvas.getContext('2d');
        
        ctx.translate(-boxX, -boxY);
        ctx.drawImage(baseImg, imgPanX, imgPanY, baseImg.width * imgScale, baseImg.height * imgScale);
        
        outCanvas.toBlob(blob => {
            resetCameraModal();
            cameraModal.classList.add('hidden');
            processMealBlob(blob);
        }, 'image/jpeg', 0.8);
    });

    async function processMealBlob(blob) {
        const mealResultCard = document.getElementById('meal-result-card');
        const mealThumbPreview = document.getElementById('meal-thumb-preview');
        
        // Show preview thumbnail from blob
        mealThumbPreview.style.backgroundImage = `url(${URL.createObjectURL(blob)})`;
        
        // UI Loading state
        const origT1 = document.getElementById('meal-drop-t1').innerText;
        document.getElementById('meal-drop-t1').innerHTML = `<svg class="spinner" style="width:16px;height:16px;animation:spin 1s linear infinite;" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" fill="none" stroke-dasharray="31" stroke-dashoffset="31"></circle></svg> Analyzing meal...`;
        document.getElementById('meal-drop-t2').innerText = "Gemini is scanning macros...";
        mealResultCard.classList.add('hidden');

        const formData = new FormData();
        formData.append('image', blob, 'meal.jpg');

        try {
            const response = await fetch('/api/meals/analyze', {
                method: 'POST',
                body: formData
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Failed to analyze meal');
            
            document.getElementById('meal-name').value = data.food_name || "Unknown Meal";
            document.getElementById('meal-conf').innerText = data.confidence_match || "Estimation";
            document.getElementById('meal-cal').value = data.calories || 0;
            document.getElementById('meal-pro').value = data.protein_g || 0;
            document.getElementById('meal-carb').value = data.carbs_g || 0;
            
            document.getElementById('meal-error').classList.add('hidden');
            mealResultCard.classList.remove('hidden');

        } catch (err) {
            const errDiv = document.getElementById('meal-error');
            errDiv.innerText = "Couldn't analyse that photo. (" + err.message + ")";
            errDiv.classList.remove('hidden');
        } finally {
            document.getElementById('meal-drop-t1').innerText = origT1;
            document.getElementById('meal-drop-t2').innerText = "Works best with one dish per frame";
            mealFileInput.value = '';
        }
    }

    document.getElementById('meal-confirm-btn')?.addEventListener('click', async () => {
        const payload = {
            food_name: document.getElementById('meal-name').value,
            confidence_match: document.getElementById('meal-conf').innerText,
            calories: document.getElementById('meal-cal').value,
            protein_g: document.getElementById('meal-pro').value,
            carbs_g: document.getElementById('meal-carb').value
        };
        try {
            const response = await fetch('/api/meals/confirm', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            if (response.ok) {
                document.getElementById('meal-result-card').classList.add('hidden');
                fetchNutrition();
            }
        } catch (e) {
            console.error('Confirm error', e);
        }
    });

    // Init App

    checkAuth();
});
