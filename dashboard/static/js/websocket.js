// WebSocket client for real-time updates

const socket = io();

socket.on('connect', function() {
    console.log('✅ Connected to trading system');
    // Update status badge
    const statusDot = document.getElementById('status-dot');
    const statusText = document.getElementById('status-text');
    const badge = document.getElementById('status-badge');
    if (statusDot && statusText && badge) {
        statusDot.className = 'status-dot status-online';
        statusText.textContent = 'ONLINE';
        badge.className = 'status-badge status-online';
    }
});

socket.on('disconnect', function() {
    console.log('❌ Disconnected from trading system');
    // Update status badge
    const statusDot = document.getElementById('status-dot');
    const statusText = document.getElementById('status-text');
    const badge = document.getElementById('status-badge');
    if (statusDot && statusText && badge) {
        statusDot.className = 'status-dot status-offline';
        statusText.textContent = 'OFFLINE';
        badge.className = 'status-badge status-offline';
    }
});

socket.on('status', function(data) {
    console.log('Status:', data);
});

// Handle real-time status updates
socket.on('status_update', function(data) {
    if (typeof loadDashboard === 'function') {
        loadDashboard();
    }
});

// Handle real-time account updates
socket.on('accounts_update', function(data) {
    if (data.accounts && data.accounts.length > 0) {
        const container = document.getElementById('accounts-container');
        if (container) {
            let html = '<div class="row">';
            let totalBalance = 0;
            let totalPnl = 0;
            let totalPositions = 0;
            
            data.accounts.forEach(account => {
                const pnl = account.unrealized_pl + account.realized_pl;
                const pnlClass = pnl >= 0 ? 'text-success' : 'text-danger';
                const pnlPct = account.balance > 0 ? ((pnl / account.balance) * 100).toFixed(2) : '0.00';
                
                totalBalance += account.balance;
                totalPnl += pnl;
                totalPositions += account.open_position_count;
                
                html += `
                    <div class="col-md-4 mb-3">
                        <div class="account-card">
                            <div class="account-header">
                                <h5>${account.name}</h5>
                                <span class="account-id">${account.id.substring(0, 8)}...</span>
                            </div>
                            <div class="account-body">
                                <div class="account-metric">
                                    <span class="metric-label">Balance</span>
                                    <span class="metric-value">$${account.balance.toFixed(2)}</span>
                                </div>
                                <div class="account-metric">
                                    <span class="metric-label">P&L</span>
                                    <span class="metric-value ${pnlClass}">$${pnl.toFixed(2)} <small>(${pnlPct}%)</small></span>
                                </div>
                                <div class="account-details">
                                    <div class="detail-item">
                                        <span>Unrealized:</span>
                                        <span class="${account.unrealized_pl >= 0 ? 'text-success' : 'text-danger'}">$${account.unrealized_pl.toFixed(2)}</span>
                                    </div>
                                    <div class="detail-item">
                                        <span>Realized:</span>
                                        <span class="${account.realized_pl >= 0 ? 'text-success' : 'text-danger'}">$${account.realized_pl.toFixed(2)}</span>
                                    </div>
                                    <div class="detail-item">
                                        <span>Open Trades:</span>
                                        <span>${account.open_trade_count}</span>
                                    </div>
                                    <div class="detail-item">
                                        <span>Margin Used:</span>
                                        <span>$${account.margin_used.toFixed(2)}</span>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                `;
            });
            html += '</div>';
            container.innerHTML = html;
            
            // Update key metrics
            const totalBalanceEl = document.getElementById('total-balance');
            const totalPnlEl = document.getElementById('total-pnl');
            const totalPositionsEl = document.getElementById('total-positions');
            
            if (totalBalanceEl) totalBalanceEl.textContent = `$${totalBalance.toFixed(2)}`;
            if (totalPnlEl) {
                totalPnlEl.textContent = `$${totalPnl.toFixed(2)}`;
                totalPnlEl.className = totalPnl >= 0 ? 'metric-value text-success' : 'metric-value text-danger';
            }
            if (totalPositionsEl) totalPositionsEl.textContent = totalPositions;
        }
    }
});

// Handle real-time position updates
socket.on('positions_update', function(data) {
    const container = document.getElementById('positions-container');
    if (!container) return;
    
    if (data.positions && data.positions.length > 0) {
        let html = '<div class="table-responsive"><table class="table table-hover"><thead><tr><th>Account</th><th>Instrument</th><th>Long</th><th>Short</th><th>Unrealized P&L</th></tr></thead><tbody>';
        data.positions.forEach(pos => {
            const pnlClass = pos.unrealized_pl >= 0 ? 'text-success' : 'text-danger';
            html += `
                <tr>
                    <td><small>${pos.account_id.substring(0, 12)}...</small></td>
                    <td><strong>${pos.instrument}</strong></td>
                    <td>${pos.long_units}</td>
                    <td>${pos.short_units}</td>
                    <td class="${pnlClass}"><strong>$${pos.unrealized_pl.toFixed(2)}</strong></td>
                </tr>
            `;
        });
        html += '</tbody></table></div>';
        container.innerHTML = html;
    } else {
        container.innerHTML = '<p class="text-muted text-center py-4">No open positions</p>';
    }
});

// Handle trade events
socket.on('trade_opened', function(data) {
    console.log('Trade opened:', data);
    if (typeof loadDashboard === 'function') {
        setTimeout(loadDashboard, 1000);
    }
});

socket.on('trade_closed', function(data) {
    console.log('Trade closed:', data);
    if (typeof loadDashboard === 'function') {
        setTimeout(loadDashboard, 1000);
    }
});
