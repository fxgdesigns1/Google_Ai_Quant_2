// WebSocket client for real-time updates

const socket = io();

socket.on('connect', function() {
    console.log('✅ Connected to trading system');
});

socket.on('disconnect', function() {
    console.log('❌ Disconnected from trading system');
});

socket.on('status', function(data) {
    console.log('Status:', data);
});

// Handle real-time status updates
socket.on('status_update', function(data) {
    if (typeof loadDashboard === 'function') {
        // Refresh dashboard data
        loadDashboard();
    }
});

// Handle real-time account updates
socket.on('accounts_update', function(data) {
    if (data.accounts && data.accounts.length > 0) {
        const container = document.getElementById('accounts-container');
        if (container) {
            let html = '<div class="row">';
            data.accounts.forEach(account => {
                const pnl = account.unrealized_pl + account.realized_pl;
                const pnlClass = pnl >= 0 ? 'text-success' : 'text-danger';
                const pnlPct = account.balance > 0 ? ((pnl / account.balance) * 100).toFixed(2) : '0.00';
                html += `
                    <div class="col-md-4 mb-3">
                        <div class="card">
                            <div class="card-header bg-primary text-white">
                                <strong>${account.name}</strong>
                            </div>
                            <div class="card-body">
                                <p><strong>Balance:</strong> $${account.balance.toFixed(2)}</p>
                                <p><strong>P&L:</strong> <span class="${pnlClass}">$${pnl.toFixed(2)} (${pnlPct}%)</span></p>
                                <p><strong>Unrealized:</strong> $${account.unrealized_pl.toFixed(2)}</p>
                                <p><strong>Realized:</strong> $${account.realized_pl.toFixed(2)}</p>
                                <p><strong>Open Trades:</strong> ${account.open_trade_count}</p>
                                <p><strong>Margin Used:</strong> $${account.margin_used.toFixed(2)}</p>
                                <p><strong>Margin Available:</strong> $${account.margin_available.toFixed(2)}</p>
                            </div>
                        </div>
                    </div>
                `;
            });
            html += '</div>';
            container.innerHTML = html;
        }
    }
});

// Handle real-time position updates
socket.on('positions_update', function(data) {
    if (data.positions && data.positions.length > 0) {
        const container = document.getElementById('positions-container');
        if (container) {
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
        }
    } else {
        const container = document.getElementById('positions-container');
        if (container) {
            container.innerHTML = '<p class="text-muted">No open positions</p>';
        }
    }
});

// Handle trade events
socket.on('trade_opened', function(data) {
    console.log('Trade opened:', data);
    // Refresh dashboard to show new trade
    if (typeof loadDashboard === 'function') {
        setTimeout(loadDashboard, 1000);
    }
});

socket.on('trade_closed', function(data) {
    console.log('Trade closed:', data);
    // Refresh dashboard to update performance
    if (typeof loadDashboard === 'function') {
        setTimeout(loadDashboard, 1000);
    }
});
