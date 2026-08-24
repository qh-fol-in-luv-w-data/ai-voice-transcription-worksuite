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
    // Add site namespace for Frappe
    // Lúc dev thì đi qua chính dev server: đường /socket.io đã được proxy
    // chuyển tiếp sang dịch vụ realtime. Trước đây chỗ này ghi cứng cổng
    // 9000, đến khi cổng đổi thì socket im lặng không kết nối được, mà lỗi
    // chỉ hiện trong console nên rất dễ bỏ qua.
    const site = window.frappe ? window.frappe.boot.sitename : window.location.hostname
    const origin = import.meta.env.DEV
      ? window.location.origin + '/ct-datalake.localhost'
      : window.location.origin + '/' + site

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
