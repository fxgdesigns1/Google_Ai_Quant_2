// Dashboard JavaScript

// WebSocket connection (handled in websocket.js)
// This file contains additional dashboard-specific functions

function formatCurrency(value) {
    return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD'
    }).format(value);
}

function formatPercent(value) {
    return (value * 100).toFixed(2) + '%';
}
