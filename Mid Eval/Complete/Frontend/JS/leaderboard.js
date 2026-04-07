// leaderboard.js

function getRankName(elo) {
    if (elo >= 2800) return "Grandmaster";
    if (elo >= 2666) return "Master III";
    if (elo >= 2533) return "Master II";
    if (elo >= 2400) return "Master I";
    if (elo >= 2300) return "Diamond III";
    if (elo >= 2200) return "Diamond II";
    if (elo >= 2100) return "Diamond I";
    if (elo >= 2000) return "Platinum III";
    if (elo >= 1900) return "Platinum II";
    if (elo >= 1800) return "Platinum I";
    if (elo >= 1700) return "Gold III";
    if (elo >= 1600) return "Gold II";
    if (elo >= 1500) return "Gold I";
    if (elo >= 1400) return "Silver III";
    if (elo >= 1300) return "Silver II";
    if (elo >= 1200) return "Silver I";
    if (elo >= 800)  return "Bronze III";
    if (elo >= 400)  return "Bronze II";
    return "Bronze I";
}

async function handleLogout(e) {
    e.preventDefault();
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

document.addEventListener('DOMContentLoaded', () => {

    // 1. AUTH GUARD (Now strictly enforced!)
    const loggedInUser = sessionStorage.getItem("arena_auth_user");
    const loggedInUid  = sessionStorage.getItem("arena_auth_uid");

    if (!loggedInUser || !loggedInUid) {
        window.location.replace("login.html");
        return;
    }

    const storedElo = parseInt(sessionStorage.getItem("arena_auth_elo") || "0");
    if (storedElo) {
        document.getElementById('header-elo-display').innerText = `${storedElo.toLocaleString()} ELO`;
        document.getElementById('header-rank-display').innerText = getRankName(storedElo);
    }

    const sidebar      = document.getElementById('sidebar');
    const sidebarToggle= document.getElementById('sidebar-toggle');
    const mainCanvas   = document.getElementById('main-canvas');
    const leaderboardBody = document.getElementById('leaderboard-body');
    const btnPrev         = document.getElementById('btn-prev');
    const btnNext         = document.getElementById('btn-next');
    const pageIndicator   = document.getElementById('page-indicator');
    const paginationInfo  = document.getElementById('pagination-info');
    const btnFilterLive   = document.getElementById('btn-filter-live');
    const btnFilterGlobal = document.getElementById('btn-filter-global');
    const btnLogout       = document.getElementById('btn-logout');
    
    // Templates
    const rowTemplate     = document.getElementById('template-table-row');
    const podiumTemplate  = document.getElementById('template-podium-card');

    const sidebarNameDisplay = document.getElementById('operator-name-display');
    const sidebarEloDisplay  = document.getElementById('operator-elo-display');
    const headerInitialsDisplay = document.getElementById('header-initials-display');

    const PLAYERS_PER_PAGE = 10;
    let currentPage   = 1;
    let currentFilter = 'global';
    
    let globalLeaderboardData = [];

    // ==========================================
    // SORTING & RANKING LOGIC
    // ==========================================
    function sortAndRankData(data) {
        // 1. Sort by ELO (descending), then by Name (alphabetical)
        data.sort((a, b) => {
            if (b.elo_rating !== a.elo_rating) {
                return b.elo_rating - a.elo_rating; // Highest ELO first
            }
            if (b.winrate !== a.winrate) {
                return b.winrate - a.winrate; // Highest win rate if ELO tied
            }
            return a.name.localeCompare(b.name);
        });

        // 2. Dynamically assign correct rankings (1, 2, 3...)
        data.forEach((player, index) => {
            player.rank = index + 1;
        });

        return data;
    }

    if (btnLogout) btnLogout.addEventListener('click', handleLogout);

    function getInitials(name) {
        if (!name) return "??";
        const parts = name.trim().split(/[_\s]+/);
        if (parts.length >= 2) return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
        return name.substring(0, 2).toUpperCase();
    }

    if (sidebarNameDisplay && loggedInUser) sidebarNameDisplay.innerText = loggedInUser.replaceAll('_', ' ').toUpperCase();
    if (headerInitialsDisplay && loggedInUser) headerInitialsDisplay.innerText = getInitials(loggedInUser);

    sidebarToggle.addEventListener('click', () => {
        if (window.innerWidth >= 768) {
            sidebar.classList.toggle('sidebar-hidden');
            mainCanvas.classList.toggle('canvas-expanded');
        } else {
            sidebar.classList.toggle('sidebar-visible');
        }
    });

    btnFilterLive.addEventListener('click', () => {
        currentFilter = 'live'; currentPage = 1;
        btnFilterLive.classList.add('active-filter');
        btnFilterGlobal.classList.remove('active-filter');
        renderTable();
    });

    btnFilterGlobal.addEventListener('click', () => {
        currentFilter = 'global'; currentPage = 1;
        btnFilterGlobal.classList.add('active-filter');
        btnFilterLive.classList.remove('active-filter');
        renderTable();
    });

    // ==========================================
    // DATA FETCHING FROM BACKEND
    // ==========================================
    function fetchLeaderboard() {
        fetch('http://localhost:5001/api/leaderboard', { credentials: 'include' })
            .then(res => {
                if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
                return res.json();
            })
            .then(data => {
                const rawData = data.players || [];
                globalLeaderboardData = sortAndRankData(rawData);

                const myData = globalLeaderboardData.find(p => p.uid === loggedInUid);
                if (myData) {
                    if (sidebarEloDisplay) sidebarEloDisplay.innerText = `${myData.elo_rating} ELO`;
                    
                    const headerEloDisplay = document.getElementById('header-elo-display');
                    const headerRankDisplay = document.getElementById('header-rank-display');
                    if (headerEloDisplay) headerEloDisplay.innerText = `${myData.elo_rating.toLocaleString()} ELO`;
                    if (headerRankDisplay) headerRankDisplay.innerText = getRankName(myData.elo_rating);
                }
                
                renderTable();
            })
            .catch(err => {
                console.error("Leaderboard fetch failed:", err);
                globalLeaderboardData = [];
                renderTable();
            });
    }

    function renderTable() {
        let filtered = currentFilter === 'live' 
            ? globalLeaderboardData.filter(p => p.status === 'online' || p.status === 'fighting') 
            : globalLeaderboardData;

        renderPodium(filtered);

        const total      = filtered.length;
        const totalPages = Math.max(1, Math.ceil(total / PLAYERS_PER_PAGE));
        const startIdx   = (currentPage - 1) * PLAYERS_PER_PAGE;
        const endIdx     = Math.min(startIdx + PLAYERS_PER_PAGE, total);
        const pageData   = filtered.slice(startIdx, endIdx);

        paginationInfo.innerText = `SHOWING ${total > 0 ? startIdx + 1 : 0} TO ${endIdx} OF ${total} ACTIVE RECORDS`;
        pageIndicator.innerText  = `PAGE ${currentPage.toString().padStart(2,'0')} / ${totalPages.toString().padStart(2,'0')}`;
        btnPrev.disabled = currentPage === 1;
        btnNext.disabled = currentPage === totalPages;

        leaderboardBody.innerHTML = '';

        if (pageData.length === 0) {
            const tr = document.createElement('tr');
            tr.innerHTML = `<td colspan="5" class="table-empty-state">NO OPERATORS FOUND</td>`;
            leaderboardBody.appendChild(tr);
            return;
        }

        const fragment = document.createDocumentFragment();

        pageData.forEach(player => {
            const isMe = player.uid === loggedInUid;
            const rowClone = rowTemplate.content.cloneNode(true);
            const tr = rowClone.querySelector('tr');

            if (isMe) tr.classList.add('is-me');

            const rankCell = rowClone.querySelector('.rank-cell');
            rankCell.textContent = player.rank.toString().padStart(2, '0');
            if (player.rank <= 3) rankCell.classList.add('rank-top-3');

            rowClone.querySelector('.player-avatar').textContent = getInitials(player.name);
            
            const nameEl = rowClone.querySelector('.player-name');
            nameEl.textContent = player.name;
            if (isMe) nameEl.classList.add('highlight');

            if (isMe) {
                rowClone.querySelector('.player-me-tag').classList.remove('hidden');
            }

            rowClone.querySelector('.player-uid').textContent = player.uid;

            const dot = rowClone.querySelector('.status-dot');
            if (player.status === 'online') {
                dot.classList.add('online');
            } else if (player.status === 'fighting') {
                dot.classList.add('fighting');
            } else {
                dot.remove(); // Removes dot node entirely for offline
            }

            const eloCell = rowClone.querySelector('.elo-cell');
            eloCell.textContent = player.elo_rating;
            if (isMe) eloCell.classList.add('highlight');

            const winrateCell = rowClone.querySelector('.winrate-cell');
            winrateCell.textContent = player.winrate + '%';
            if (isMe) winrateCell.classList.add('highlight');

            fragment.appendChild(rowClone);
        });

        leaderboardBody.appendChild(fragment);
    }

    function renderPodium(players) {
        const podium = document.getElementById('podium');
        if (!podium) return;

        const top3 = players.slice(0, 3);
        if (top3.length === 0) {
            podium.innerHTML = `<div class="podium-empty-state">NO DATA YET</div>`;
            return;
        }

        const configs = [
            { pos: "02", cls: "rank-2" },
            { pos: "01", cls: "rank-1" },
            { pos: "03", cls: "rank-3" },
        ];

        podium.innerHTML = '';
        const slots = [
            { player: top3[1], cfg: configs[0] },
            { player: top3[0], cfg: configs[1] },
            { player: top3[2], cfg: configs[2] },
        ];

        const fragment = document.createDocumentFragment();

        slots.forEach(({ player, cfg }) => {
            if (!player) return;
            
            const podClone = podiumTemplate.content.cloneNode(true);
            const card = podClone.querySelector('.podium-card');
            
            card.classList.add(cfg.cls);
            podClone.querySelector('.podium-bg-number').textContent = cfg.pos;
            podClone.querySelector('.podium-avatar').textContent = getInitials(player.name);
            podClone.querySelector('.podium-rank-badge').textContent = player === top3[0] ? 'World_Apex' : getRankName(player.elo_rating);
            podClone.querySelector('.podium-name').textContent = player.name;
            podClone.querySelector('.podium-uid').textContent = player.uid;
            podClone.querySelector('.elo').textContent = player.elo_rating.toLocaleString();
            podClone.querySelector('.winrate').textContent = player.winrate + '%';

            fragment.appendChild(podClone);
        });

        podium.appendChild(fragment);
    }

    btnNext.addEventListener('click', () => {
        const filtered = currentFilter === 'live' ? globalLeaderboardData.filter(p => p.status === 'online' || p.status === 'fighting') : globalLeaderboardData;
        const totalPages = Math.ceil(filtered.length / PLAYERS_PER_PAGE);
        if (currentPage < totalPages) { currentPage++; renderTable(); }
    });
    btnPrev.addEventListener('click', () => { if (currentPage > 1) { currentPage--; renderTable(); } });

    // Initial load fetch
    fetchLeaderboard();
});

let isNavigating = false;
document.addEventListener('click', (e) => { if (e.target.closest('a')) isNavigating = true; });

window.addEventListener('beforeunload', () => {
    if (isNavigating) return;
    const myUid = sessionStorage.getItem("arena_auth_uid");
    if (myUid) {
        fetch('http://localhost:5001/logout', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ uid: myUid }), keepalive: true 
        }).catch(() => {});
    }
});