// lobby_command_center.js

document.addEventListener('DOMContentLoaded', () => {

    // ==========================================
    // 1. AUTH GUARD
    // ==========================================
    const loggedInUser = sessionStorage.getItem("arena_auth_user");
    const loggedInUid  = sessionStorage.getItem("arena_auth_uid");

    if (!loggedInUser || !loggedInUid) {
        console.warn("SECURITY: Unauthorised access. Redirecting.");
        window.location.replace("login.html");
        return;
    }

    // ==========================================
    // 2. DOM ELEMENTS & STATE
    // ==========================================
    const searchInput  = document.getElementById('player-search');
    const mobileSearchInput = document.getElementById('player-search-mobile');
    const sortSelect   = document.getElementById('sort-select');
    const playerGrid   = document.getElementById('player-grid');
    const btnFilterAll = document.getElementById('btn-filter-all');
    const btnFilterGM  = document.getElementById('btn-filter-gm');
    const sidebar      = document.getElementById('sidebar');
    const sidebarToggle= document.getElementById('sidebar-toggle');
    const mainCanvas   = document.getElementById('main-canvas');
    const onlineCountDisplay = document.getElementById('online-count');
    
    let activeFilter   = 'all';
    let isMatchRunning = false;
    let globalPlayersData = [];

    setupHeaders();

    // ==========================================
    // 3. EVENT LISTENERS
    // ==========================================
    sidebarToggle.addEventListener('click', () => {
        if (isMatchRunning) {
            alert("⚠️ SYSTEM LOCKED: Active match in progress.");
            return;
        }
        if (window.innerWidth >= 768) {
            sidebar.classList.toggle('sidebar-hidden');
            mainCanvas.classList.toggle('canvas-expanded');
        } else {
            sidebar.classList.toggle('sidebar-visible');
        }
    });

    // Semantic Class toggling instead of Tailwind replacement
    btnFilterAll.addEventListener('click', () => {
        activeFilter = 'all';
        btnFilterAll.classList.add('active');
        btnFilterGM.classList.remove('active');
        renderGrid();
    });

    btnFilterGM.addEventListener('click', () => {
        activeFilter = 'gm';
        btnFilterGM.classList.add('active');
        btnFilterAll.classList.remove('active');
        renderGrid();
    });

    searchInput.addEventListener('input', renderGrid);
    sortSelect.addEventListener('change', renderGrid);
    document.getElementById('btn-logout').addEventListener('click', handleLogout);

    if (mobileSearchInput) {
        mobileSearchInput.addEventListener('input', (e) => {
            searchInput.value = e.target.value;
            renderGrid();
        });
    }

    // ==========================================
    // 4. LOGIC HELPERS
    // ==========================================
    function getInitials(name) {
        if (!name) return "??";
        const parts = name.trim().split(/[_\s]+/);
        if (parts.length >= 2) {
            return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
        }
        return name.substring(0, 2).toUpperCase();
    }

    function getRank(elo) {
        if (elo >= 2800) return { name: "GRANDMASTER",  cls: "rank-gm" };
        if (elo >= 2666) return { name: "MASTER III",   cls: "rank-master" };
        if (elo >= 2533) return { name: "MASTER II",    cls: "rank-master" };
        if (elo >= 2400) return { name: "MASTER I",     cls: "rank-master" };
        if (elo >= 2300) return { name: "DIAMOND III",  cls: "rank-diamond" };
        if (elo >= 2200) return { name: "DIAMOND II",   cls: "rank-diamond" };
        if (elo >= 2100) return { name: "DIAMOND I",    cls: "rank-diamond" };
        if (elo >= 2000) return { name: "PLATINUM III", cls: "rank-platinum" };
        if (elo >= 1900) return { name: "PLATINUM II",  cls: "rank-platinum" };
        if (elo >= 1800) return { name: "PLATINUM I",   cls: "rank-platinum" };
        if (elo >= 1700) return { name: "GOLD III",     cls: "rank-gold" };
        if (elo >= 1600) return { name: "GOLD II",      cls: "rank-gold" };
        if (elo >= 1500) return { name: "GOLD I",       cls: "rank-gold" };
        if (elo >= 1400) return { name: "SILVER III",   cls: "rank-silver" };
        if (elo >= 1300) return { name: "SILVER II",    cls: "rank-silver" };
        if (elo >= 1200) return { name: "SILVER I",     cls: "rank-silver" };
        if (elo >= 800)  return { name: "BRONZE III",   cls: "rank-bronze" };
        if (elo >= 400)  return { name: "BRONZE II",    cls: "rank-bronze" };
        return                  { name: "BRONZE I",     cls: "rank-bronze" };
    }

    function setupHeaders() {
        const loggedInElo = sessionStorage.getItem("arena_auth_elo");
        const rankInfo = getRank(parseInt(loggedInElo || "0"));

        document.getElementById('header-initials-display').textContent = getInitials(loggedInUser);
        document.getElementById('operator-name-display').textContent = loggedInUser.replaceAll('_', ' ').toUpperCase();
        
        if (loggedInElo) {
            document.getElementById('operator-elo-display').textContent = `${loggedInElo} ELO`;
            document.getElementById('header-elo-display').textContent = `${loggedInElo} ELO`;
            document.getElementById('header-rank-display').textContent = rankInfo.name;
        }
    }

    // ==========================================
    // 5. BACKEND FETCHING
    // ==========================================
    function fetchPlayers() {
        fetch('http://localhost:5001/api/players', { credentials: 'include' })
            .then(response => {
                if (!response.ok) throw new Error(`Server error: ${response.status}`);
                return response.json();
            })
            .then(data => {
                globalPlayersData = data.players || [];
                renderGrid();
            })
            .catch(error => {
                console.warn("Backend unavailable:", error);
                globalPlayersData = [];
                renderGrid();
            });
    }

    // ==========================================
    // 6. RENDER GRID (TRADITIONAL DOM MANIPULATION)
    // ==========================================
    function renderGrid() {
        const searchTerm = searchInput.value.toLowerCase();
        const template = document.getElementById('player-card-template');

        let filtered = globalPlayersData.filter(p =>
            p.name.toLowerCase().includes(searchTerm)
        );

        if (activeFilter === 'gm') {
            filtered = filtered.filter(p => p.elo_rating >= 2800);
        }

        if (onlineCountDisplay) {
            const onlineCount = globalPlayersData.filter(p => p.status === 'online' || p.status === 'fighting').length;
            onlineCountDisplay.textContent = `${onlineCount} ONLINE`;
        }

        const statusWeight = { "online": 1, "fighting": 2, "offline": 3 };
        const sortMode = sortSelect.value;
        
        filtered.sort((a, b) => {
            const isMeA = (a.uid === loggedInUid);
            const isMeB = (b.uid === loggedInUid);
            if (isMeA && !isMeB) return -1;
            if (!isMeA && isMeB) return 1;

            const weightA = statusWeight[a.status] || 3;
            const weightB = statusWeight[b.status] || 3;
            if (weightA !== weightB) { return weightA - weightB; }

            switch (sortMode) {
                case 'elo-desc':  return b.elo_rating - a.elo_rating;
                case 'elo-asc':   return a.elo_rating - b.elo_rating;
                case 'win-desc':  return b.winrate - a.winrate;
                case 'win-asc':   return a.winrate - b.winrate;
                case 'name-asc':  return a.name.localeCompare(b.name);
                case 'name-desc': return b.name.localeCompare(a.name);
                default:          return 0;
            }
        });

        playerGrid.innerHTML = '';

        if (filtered.length === 0) {
            const emptyTemplate = document.getElementById('empty-state-template');
            playerGrid.appendChild(emptyTemplate.content.cloneNode(true));
            return;
        }

        filtered.forEach(player => {
            const clone = template.content.cloneNode(true);
            const cardWrapper = clone.querySelector('.player-card');
            const rankData = getRank(player.elo_rating);
            const isMe = (player.uid === loggedInUid);

            // Populate Text Data
            clone.querySelector('.js-initials').textContent = getInitials(player.name);
            clone.querySelector('.js-rank').textContent = rankData.name;
            clone.querySelector('.js-rank').classList.add(rankData.cls);
            clone.querySelector('.js-elo').textContent = `${player.elo_rating} ELO`;
            clone.querySelector('.js-winrate').textContent = `WR: ${player.winrate}%`;
            clone.querySelector('.js-name').textContent = player.name;
            clone.querySelector('.js-uid').textContent = player.uid;

            // Handle State Logics using simple CSS classes
            const btnIcon = clone.querySelector('.js-btn-icon');
            const btnText = clone.querySelector('.js-btn-text');
            const statusText = clone.querySelector('.js-status-text');

            if (player.status === "fighting") {
                cardWrapper.classList.add('state-fighting');
                statusText.textContent = "FIGHTING";
                btnIcon.style.display = "none";
                btnText.textContent = "MATCH IN PROGRESS";
                clone.querySelector('.js-btn').disabled = true;

            } else if (player.status === "online") {
                if (isMe) {
                    cardWrapper.classList.add('state-online-me');
                    statusText.textContent = "YOU — ONLINE";
                    btnIcon.style.display = "none";
                    btnText.textContent = "THIS IS YOU";
                    clone.querySelector('.js-btn').disabled = true;
                } else {
                    cardWrapper.classList.add('state-online');
                    statusText.textContent = "ONLINE";
                    btnIcon.textContent = "swords";
                    btnText.textContent = "CHALLENGE";
                }
            } else {
                cardWrapper.classList.add('state-offline');
                statusText.textContent = "OFFLINE";
                clone.querySelector('.status-dot').style.display = "none";
                btnIcon.style.display = "none";
                btnText.textContent = "UNAVAILABLE";
                clone.querySelector('.js-btn').disabled = true;
            }

            playerGrid.appendChild(clone);
        });
    }

    // Start App Logic
    fetchPlayers();
    setInterval(fetchPlayers, 5000);
});

// ==========================================
// 7. LOGOUT & GHOST USER PREVENTION
// ==========================================
async function handleLogout(e) {
    if(e) e.preventDefault();
    const myUid = sessionStorage.getItem("arena_auth_uid"); 
    try {
        await fetch('http://localhost:5001/logout', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ uid: myUid }),
            credentials: 'include'
        });
    } catch (_) {}
    sessionStorage.clear();
    window.location.href = 'login.html';
}

let isNavigating = false;

document.addEventListener('click', (e) => {
    if (e.target.closest('a')) {
        isNavigating = true; 
    }
});

window.addEventListener('beforeunload', () => {
    if (isNavigating) return; 

    const myUid = sessionStorage.getItem("arena_auth_uid");
    
    if (myUid) {
        fetch('http://localhost:5001/logout', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ uid: myUid }),
            keepalive: true 
        }).catch(() => {}); 
    }
});