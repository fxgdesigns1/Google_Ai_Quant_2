// WebSocket client for real-time updates

const socket = io();

socket.on('connect', function() {
    console.log('✅ Connected to trading system');
});

socket.on('disconnect', function() {
    console.log('❌ Disconnected from trading system');
});

socket.on('status', function(data) {
    console.log('Status update:', data);
});

// Handle real-time position updates
socket.on('positions_update', function(data) {
    console.log('Position update:', data);
    // If we're on the positions page, refresh it
    if (window.location.pathname === '/positions' || window.location.pathname === '/') {
        // Trigger a refresh of positions (for positions page)
        if (typeof loadPositions === 'function') {
            loadPositions();
        }
        // Trigger dashboard refresh (for main dashboard)
        if (typeof loadDashboard === 'function') {
            // Only reload positions part of dashboard
            fetch('/api/positions')
                .then(r => r.json())
                .then(data => {
                    const container = document.getElementById('positions-container');
                    if (container && data.positions && data.positions.length > 0) {
                        let html = '<table class="table table-striped"><thead><tr><th>Account</th><th>Instrument</th><th>Long Units</th><th>Short Units</th><th>Unrealized P&L</th></tr></thead><tbody>';
                        data.positions.forEach(pos => {
                            const pnlClass = pos.unrealized_pl >= 0 ? 'text-success' : 'text-danger';
                            html += `
                                <tr>
                                    <td>${pos.account_id.substring(0, 15)}...</td>
                                    <td>${pos.instrument}</td>
                                    <td>${pos.long_units}</td>
                                    <td>${pos.short_units}</td>
                                    <td class="${pnlClass}">$${pos.unrealized_pl.toFixed(2)}</td>
                                </tr>
                            `;
                        });
                        html += '</tbody></table>';
                        container.innerHTML = html;
                    } else if (container) {
                        container.innerHTML = '<p class="text-muted">No open positions</p>';
                    }
                })
                .catch(e => console.error('Error updating positions:', e));
        }
    }
});

// Handle system status updates
socket.on('system_status', function(data) {
    console.log('System status update:', data);
    // Update status indicator if on dashboard
    if (window.location.pathname === '/') {
        const indicator = document.getElementById('status-indicator');
        if (indicator && data.market_data_running) {
            indicator.className = 'badge bg-success';
            indicator.textContent = 'ONLINE';
        }
        const marketDataStatus = document.getElementById('market-data-status');
        if (marketDataStatus) {
            marketDataStatus.textContent = data.market_data_running ? 'Running' : 'Stopped';
        }
    }
});

socket.on('trade_opened', function(data) {
    console.log('Trade opened:', data);
    // Show notification or update UI
    if (typeof loadDashboard === 'function') {
        loadDashboard();
    }
});

socket.on('trade_closed', function(data) {
    console.log('Trade closed:', data);
    // Show notification or update UI
    if (typeof loadDashboard === 'function') {
        loadDashboard();
    }
});
