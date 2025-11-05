// WebSocket client for real-time updates

const socket = io();

socket.on('connect', function() {
    console.log('Connected to trading system');
});

socket.on('disconnect', function() {
    console.log('Disconnected from trading system');
});

socket.on('status', function(data) {
    console.log('Status update:', data);
    if (data.system_connected === false) {
        console.warn('System not connected - dashboard running in limited mode');
    }
});

// Handle real-time market data updates
socket.on('market_update', function(data) {
    console.log('Market update:', data);
    // Update market data in UI if handler exists
    if (typeof handleMarketUpdate === 'function') {
        handleMarketUpdate(data.prices);
    }
});

// Handle real-time position updates
socket.on('position_update', function(data) {
    console.log('Position update:', data);
    // Trigger dashboard refresh if on positions page
    if (typeof loadDashboard === 'function') {
        // Only reload positions, not everything
        if (typeof loadPositions === 'function') {
            loadPositions();
        } else {
            // Fallback to full dashboard reload
            loadDashboard();
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
