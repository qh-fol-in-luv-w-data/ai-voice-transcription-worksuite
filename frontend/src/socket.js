// io is provided globally via CDN in index.html

// Detect if we are on a dev server (e.g., Vite 5173) or production (80/443)
// If production, socket usually runs on the same host but Frappe Nginx handles /socket.io
// If no Nginx, it might be on port 9000. We will try default first.
const getSocketUrl = () => {
  if (window.location.port === "5173" || window.location.port === "8080") {
    // Dev environment, fallback to Frappe backend port usually 8000/9000
    return window.location.protocol + "//" + window.location.hostname + ":9000";
  }
  return window.location.origin;
};

export const socket = window.io(getSocketUrl(), {
  withCredentials: true,
  reconnection: true,
  reconnectionAttempts: 5,
  reconnectionDelay: 1000,
});

socket.on("connect", () => {
  console.log("Socket.IO connected to Frappe:", socket.id);
});

socket.on("connect_error", (err) => {
  console.error("Socket.IO connection error:", err.message);
});
