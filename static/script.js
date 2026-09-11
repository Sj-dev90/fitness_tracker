document.addEventListener('DOMContentLoaded', () => {
    // --- Theme Toggle Logic ---
    const themeToggleBtn = document.getElementById('theme-toggle');
    const currentTheme = localStorage.getItem('theme');
    
    // Apply saved theme on load (default to dark if not set, or light if preferred)
    if (currentTheme) {
        document.body.setAttribute('data-theme', currentTheme);
    } else {
        // Default to dark mode if no preference
        document.body.setAttribute('data-theme', 'dark');
    }

    themeToggleBtn.addEventListener('click', () => {
        let theme = document.body.getAttribute('data-theme');
        if (theme === 'dark') {
            document.body.removeAttribute('data-theme');
            localStorage.setItem('theme', 'light');
        } else {
            document.body.setAttribute('data-theme', 'dark');
            localStorage.setItem('theme', 'dark');
        }
    });
    // ---------------------------

    const API_URL = '/api/workouts';
    
    // DOM Elements
    const workoutForm = document.getElementById('workout-form');
    const workoutList = document.getElementById('workout-list');
    const formTitle = document.getElementById('form-title');
    const submitBtn = document.getElementById('submit-btn');
    const cancelBtn = document.getElementById('cancel-btn');
    
    // Form Inputs
    const idInput = document.getElementById('workout-id');
    const nameInput = document.getElementById('exercise_name');
    const setsInput = document.getElementById('sets');
    const repsInput = document.getElementById('reps');
    const weightInput = document.getElementById('weight_kg');
    const dateInput = document.getElementById('date');

    // Set default date to today
    dateInput.valueAsDate = new Date();

    // Fetch and display workouts on load
    fetchWorkouts();

    // Form Submit Event (Create or Update)
    workoutForm.addEventListener('submit', async (e) => {
        e.preventDefault();

        const workoutData = {
            exercise_name: nameInput.value,
            sets: setsInput.value,
            reps: repsInput.value,
            weight_kg: weightInput.value,
            date: dateInput.value
        };

        const workoutId = idInput.value;

        if (workoutId) {
            // Update existing workout
            await updateWorkout(workoutId, workoutData);
        } else {
            // Create new workout
            await createWorkout(workoutData);
        }

        // Reset form and reload list
        resetForm();
        fetchWorkouts();
    });

    // Cancel Edit Event
    cancelBtn.addEventListener('click', resetForm);

    // --- API Interactions ---

    async function fetchWorkouts() {
        try {
            const response = await fetch(API_URL);
            if (!response.ok) throw new Error('Failed to fetch workouts');
            const workouts = await response.json();
            renderWorkouts(workouts);
        } catch (error) {
            console.error('Error fetching workouts:', error);
            workoutList.innerHTML = '<p style="color: red;">Failed to load workouts. Is the server running?</p>';
        }
    }

    async function createWorkout(data) {
        try {
            const response = await fetch(API_URL, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });
            if (!response.ok) throw new Error('Failed to create workout');
        } catch (error) {
            console.error('Error creating workout:', error);
            alert('Failed to save workout.');
        }
    }

    async function updateWorkout(id, data) {
        try {
            const response = await fetch(`${API_URL}/${id}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });
            if (!response.ok) throw new Error('Failed to update workout');
        } catch (error) {
            console.error('Error updating workout:', error);
            alert('Failed to update workout.');
        }
    }

    async function deleteWorkout(id) {
        if (!confirm('Are you sure you want to delete this workout?')) return;
        
        try {
            const response = await fetch(`${API_URL}/${id}`, {
                method: 'DELETE'
            });
            if (!response.ok) throw new Error('Failed to delete workout');
            fetchWorkouts(); // Reload list
        } catch (error) {
            console.error('Error deleting workout:', error);
            alert('Failed to delete workout.');
        }
    }

    // --- UI Helpers ---

    function renderWorkouts(workouts) {
        workoutList.innerHTML = '';
        
        if (workouts.length === 0) {
            workoutList.innerHTML = '<p>No workouts logged yet. Start lifting!</p>';
            return;
        }

        // Sort by date descending
        workouts.sort((a, b) => new Date(b.date) - new Date(a.date));

        workouts.forEach(workout => {
            const card = document.createElement('div');
            card.className = 'workout-card';
            
            // Format date nicely
            const dateObj = new Date(workout.date);
            const formattedDate = dateObj.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });

            card.innerHTML = `
                <div class="workout-header">
                    <h3>${workout.exercise_name}</h3>
                    <span class="workout-date">${formattedDate}</span>
                </div>
                <div class="workout-stats">
                    <div class="stat">
                        <span class="stat-value">${workout.sets}</span>
                        <span class="stat-label">Sets</span>
                    </div>
                    <div class="stat">
                        <span class="stat-value">${workout.reps}</span>
                        <span class="stat-label">Reps</span>
                    </div>
                    <div class="stat">
                        <span class="stat-value">${workout.weight_kg}</span>
                        <span class="stat-label">kg</span>
                    </div>
                </div>
                <div class="workout-actions">
                    <button class="btn edit-btn" onclick="editWorkout('${workout._id}', '${workout.exercise_name}', ${workout.sets}, ${workout.reps}, ${workout.weight_kg}, '${workout.date}')">Edit</button>
                    <button class="btn danger-btn" onclick="deleteWorkoutHandler('${workout._id}')">Delete</button>
                </div>
            `;
            workoutList.appendChild(card);
        });
    }

    function resetForm() {
        workoutForm.reset();
        idInput.value = '';
        dateInput.valueAsDate = new Date();
        formTitle.textContent = 'Log New Workout';
        submitBtn.textContent = 'Save Workout';
        cancelBtn.classList.add('hidden');
        window.scrollTo(0, 0);
    }

    // Expose functions to global scope for inline HTML event handlers (onclick)
    window.editWorkout = function(id, name, sets, reps, weight, date) {
        idInput.value = id;
        nameInput.value = name;
        setsInput.value = sets;
        repsInput.value = reps;
        weightInput.value = weight;
        dateInput.value = date;
        
        formTitle.textContent = 'Edit Workout';
        submitBtn.textContent = 'Update Workout';
        cancelBtn.classList.remove('hidden');
        window.scrollTo(0, 0);
    };

    window.deleteWorkoutHandler = function(id) {
        deleteWorkout(id);
    };
});
