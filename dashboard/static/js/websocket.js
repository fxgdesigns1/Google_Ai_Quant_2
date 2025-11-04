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
});

// Handle real-time updates
socket.on('position_update', function(data) {
    // Update position data in UI
    console.log('Position update:', data);
});

socket.on('trade_opened', function(data) {
    console.log('Trade opened:', data);
});

socket.on('trade_closed', function(data) {
    console.log('Trade closed:', data);
});
