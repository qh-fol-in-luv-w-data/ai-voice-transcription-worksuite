export const initSocket = () => {
  if (window.frappe && window.frappe.realtime) {
    console.log("Socket initialized via frappe.realtime");
    return window.frappe.realtime;
  }
  console.warn("frappe.realtime not found. WebSockets may not work.");
  return null;
}

export const onSocketEvent = (event, callback) => {
  if (window.frappe && window.frappe.realtime) {
    window.frappe.realtime.on(event, callback);
  }
}

export const offSocketEvent = (event, callback) => {
  if (window.frappe && window.frappe.realtime) {
    window.frappe.realtime.off(event, callback);
  }
}
