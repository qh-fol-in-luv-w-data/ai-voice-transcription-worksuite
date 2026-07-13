import { io } from 'socket.io-client'

let _socket = null
let _user = null

function _getSocket() {
  // Nếu chạy trong Frappe web context thì dùng frappe.realtime
  if (window.frappe && window.frappe.realtime) {
    return null // frappe.realtime.on/off dùng trực tiếp
  }

  // Standalone Vite dev mode — tự kết nối socket.io
  if (!_socket) {
    const origin = import.meta.env.DEV
      ? 'http://ct-datalake.localhost:9000'
      : window.location.origin

    _socket = io(origin, {
      withCredentials: true,
      transports: ['websocket', 'polling'],
    })

    _socket.on('connect', () => {
      console.log('[Socket] Connected:', _socket.id)
    })

    _socket.on('connect_error', (err) => {
      console.warn('[Socket] connect_error:', err.message)
    })
  }
  return _socket
}

export const initSocket = () => {
  return _getSocket()
}

export const onSocketEvent = (event, callback) => {
  if (window.frappe && window.frappe.realtime) {
    window.frappe.realtime.on(event, callback)
    return
  }
  const sock = _getSocket()
  if (sock) {
    sock.on(event, callback)
  }
}

export const offSocketEvent = (event, callback) => {
  if (window.frappe && window.frappe.realtime) {
    window.frappe.realtime.off(event, callback)
    return
  }
  const sock = _getSocket()
  if (sock) {
    sock.off(event, callback)
  }
}
