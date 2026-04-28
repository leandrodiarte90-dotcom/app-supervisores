
/* ============================================================
   App Supervisores - UI base + WebSocket Realtime Chat
   Pegar/reemplazar en: static/js/app.js
   ============================================================ */

document.addEventListener('DOMContentLoaded', function () {
    inicializarTablasResponsive();
    inicializarEvidencias();
    iniciarNotificacionesSupervisores();
    iniciarRealtimeChat();
});

function inicializarTablasResponsive() {
    document.querySelectorAll('table').forEach(function(table) {
        if (!table.parentElement.classList.contains('table-responsive')) {
            const wrapper = document.createElement('div');
            wrapper.className = 'table-responsive';
            table.parentNode.insertBefore(wrapper, table);
            wrapper.appendChild(table);
        }
        table.classList.add('table', 'table-hover', 'align-middle');
    });
}

function inicializarEvidencias() {
    document.querySelectorAll('[data-evidence-src]').forEach(function(link) {
        link.addEventListener('click', function(ev) {
            ev.preventDefault();
            const img = document.getElementById('evidenceModalImg');
            if (!img || typeof bootstrap === 'undefined') return;
            img.src = link.getAttribute('data-evidence-src');
            const modal = new bootstrap.Modal(document.getElementById('evidenceModal'));
            modal.show();
        });
    });
}

/* ============================================================
   Notificaciones existentes por polling
   Se mantiene como fallback junto con WebSocket.
   ============================================================ */
function iniciarNotificacionesSupervisores() {
    const navbar = document.getElementById('mainNavbar');
    if (!navbar) return;

    const audio = new Audio('/static/sounds/notification.mp3');
    audio.preload = 'auto';
    audio.loop = false;

    let sonidoHabilitado = localStorage.getItem('notif_sonido_habilitado') === '1';
    let reproduciendoSonido = false;

    const item = document.createElement('li');
    item.className = 'nav-item';
    item.innerHTML = `
        <button type="button" id="notifEnableBtn" class="nav-link notif-enable-btn">
            🔔 Notificaciones
        </button>
    `;

    const navList = navbar.querySelector('.navbar-nav');
    if (navList && !document.getElementById('notifEnableBtn')) {
        navList.insertBefore(item, navList.lastElementChild);
    }

    const btn = document.getElementById('notifEnableBtn');

    const setBtnState = () => {
        if (!btn) return;

        if (!('Notification' in window)) {
            btn.textContent = '🔕 Sin soporte';
            btn.disabled = true;
            return;
        }

        if (Notification.permission === 'granted' && sonidoHabilitado) {
            btn.textContent = '🔔 Activas';
        } else if (Notification.permission === 'denied') {
            btn.textContent = '🔕 Bloqueadas';
        } else {
            btn.textContent = '🔔 Activar';
        }
    };

    if (btn) {
        btn.addEventListener('click', async function () {
            sonidoHabilitado = true;
            localStorage.setItem('notif_sonido_habilitado', '1');

            try {
                audio.loop = false;
                audio.pause();
                audio.currentTime = 0;
                await audio.play();
                setTimeout(() => {
                    audio.pause();
                    audio.currentTime = 0;
                }, 700);
            } catch (e) {}

            if ('Notification' in window && Notification.permission === 'default') {
                await Notification.requestPermission();
            }

            setBtnState();
        });
    }

    setBtnState();

    // En móviles, el audio solo se habilita después de una interacción del usuario.
    // Si el usuario toca cualquier parte de la app y todavía no activó desde el botón,
    // dejamos el sonido preparado para los siguientes eventos realtime.
    function habilitarSonidoPorInteraccion() {
        if (!sonidoHabilitado) {
            sonidoHabilitado = true;
            localStorage.setItem("notif_sonido_habilitado", "1");
            setBtnState();
        }
        document.removeEventListener("click", habilitarSonidoPorInteraccion);
        document.removeEventListener("touchstart", habilitarSonidoPorInteraccion);
    }
    document.addEventListener("click", habilitarSonidoPorInteraccion, { once: true });
    document.addEventListener("touchstart", habilitarSonidoPorInteraccion, { once: true });

    window.reproducirSonidoNotificacion = function reproducirSonido() {
        if (!sonidoHabilitado || reproduciendoSonido) return;

        reproduciendoSonido = true;

        try {
            audio.loop = false;
            audio.pause();
            audio.currentTime = 0;

            audio.play().catch(() => {
                reproduciendoSonido = false;
            });

            setTimeout(() => {
                audio.pause();
                audio.currentTime = 0;
                reproduciendoSonido = false;
            }, 2500);
        } catch (e) {
            reproduciendoSonido = false;
        }
    };

    async function inicializarUltimoId() {
        if (localStorage.getItem('ultimo_notif_id')) return;

        try {
            const resp = await fetch('/api/notificaciones/ultimo', { cache: 'no-store' });
            if (!resp.ok) return;

            const data = await resp.json();
            localStorage.setItem('ultimo_notif_id', String(data.ultimo_id || 0));
        } catch (e) {}
    }

    async function consultarNotificaciones() {
        const ultimo = parseInt(localStorage.getItem('ultimo_notif_id') || '0', 10);

        try {
            const resp = await fetch(`/api/notificaciones?after=${ultimo}`, { cache: 'no-store' });
            if (!resp.ok) return;

            const data = await resp.json();

            if (!data.ok || !Array.isArray(data.notificaciones)) return;

            let nuevoUltimo = ultimo;

            data.notificaciones.forEach((n) => {
                const id = Number(n.id || 0);
                if (id > ultimo) {
                    nuevoUltimo = Math.max(nuevoUltimo, id);

                    // No reproducir ni mostrar notificaciones propias; además evitamos duplicados entre polling y WebSocket.
                    if (eventoEsPropio(n) || notificacionYaVista(id)) return;
                    marcarNotificacionVista(id);

                    mostrarToastInterno(n.titulo || 'App Supervisores', n.cuerpo || '', n.observacion_id);
                    if (window.reproducirSonidoNotificacion) window.reproducirSonidoNotificacion();
                }
            });

            localStorage.setItem('ultimo_notif_id', String(nuevoUltimo));
        } catch (e) {}
    }

    inicializarUltimoId().then(() => {
        setInterval(consultarNotificaciones, 9000);
    });
}

/* ============================================================
   WebSocket Chat Realtime
   ============================================================ */

let realtimeSocket = null;
let realtimeReconnectTimer = null;
let realtimeReconnectAttempts = 0;
let realtimeOnlineUsers = [];

function usuarioActualNombre() {
    return (window.APP_USER && window.APP_USER.nombre) ? String(window.APP_USER.nombre) : "";
}

function eventoEsPropio(data) {
    const actual = usuarioActualNombre();
    if (!actual || !data) return false;
    const from = data.from || data.usuario || (data.message && data.message.remitente) || (data.observacion && data.observacion.creado_por);
    return String(from || "") === actual;
}

function notificacionYaVista(id) {
    if (!id) return false;
    const vistas = JSON.parse(localStorage.getItem("notif_ids_mostradas") || "[]");
    return vistas.includes(String(id));
}

function marcarNotificacionVista(id) {
    if (!id) return;
    const vistas = JSON.parse(localStorage.getItem("notif_ids_mostradas") || "[]");
    const sid = String(id);
    if (!vistas.includes(sid)) vistas.push(sid);
    while (vistas.length > 80) vistas.shift();
    localStorage.setItem("notif_ids_mostradas", JSON.stringify(vistas));
}

function iniciarRealtimeChat() {
    const user = window.APP_USER || {};
    if (!user.nombre) return;

    crearChatWidget();
    conectarWebSocket(user.nombre);
}

function conectarWebSocket(userId) {
    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const wsUrl = `${protocol}://${window.location.host}/ws/${encodeURIComponent(userId)}`;

    try {
        realtimeSocket = new WebSocket(wsUrl);
    } catch (e) {
        actualizarEstadoRealtime(false);
        return;
    }

    realtimeSocket.onopen = () => {
        realtimeReconnectAttempts = 0;
        actualizarEstadoRealtime(true);
        cargarUsuariosChat();
    };

    realtimeSocket.onmessage = (event) => {
        let data = null;

        try {
            data = JSON.parse(event.data);
        } catch (e) {
            return;
        }

        manejarEventoRealtime(data);
    };

    realtimeSocket.onclose = () => {
        actualizarEstadoRealtime(false);
        programarReconexion(userId);
    };

    realtimeSocket.onerror = () => {
        actualizarEstadoRealtime(false);
        try { realtimeSocket.close(); } catch (e) {}
    };
}

function programarReconexion(userId) {
    if (realtimeReconnectTimer) return;

    realtimeReconnectAttempts += 1;
    const delay = Math.min(30000, 2000 * realtimeReconnectAttempts);

    realtimeReconnectTimer = setTimeout(() => {
        realtimeReconnectTimer = null;
        conectarWebSocket(userId);
    }, delay);
}

function manejarEventoRealtime(data) {
    if (data.type === 'chat_history') {
        const mensajes = Array.isArray(data.messages) ? data.messages : [];
        mensajes.forEach((m) => agregarMensajeChat(m, false));
        scrollChatAlFinal();
        return;
    }

    if (data.type === 'online_status') {
        realtimeOnlineUsers = Array.isArray(data.online) ? data.online : [];
        actualizarUsuariosOnline();
        return;
    }

    if (data.type === 'chat_message') {
        agregarMensajeChat(data.message, true);

        const actual = (window.APP_USER || {}).nombre;
        if (data.message && data.message.remitente !== actual) {
            mostrarToastInterno(
                'App Supervisores',
                `${data.message.remitente}: ${data.message.mensaje}`,
                data.message.observacion_id
            );
            if (window.reproducirSonidoNotificacion) window.reproducirSonidoNotificacion();
        }
        return;
    }

    if (data.type === 'nueva_observacion') {
        manejarNuevaObservacionRealtime(data);
        return;
    }

    if (data.type === 'observation_event') {
        manejarEventoObservacionGenerico(data);
        return;
    }

    if (data.type === 'error') {
        mostrarToastInterno('App Supervisores', data.message || 'Error realtime', null);
    }
}

function crearChatWidget() {
    if (document.getElementById('realtimeChatWidget')) return;

    const wrapper = document.createElement('div');
    wrapper.id = 'realtimeChatWidget';
    wrapper.className = 'rt-chat collapsed';

    const users = Array.isArray(window.APP_USERS) ? window.APP_USERS : [];
    const userOptions = users
        .filter(u => u.nombre !== (window.APP_USER || {}).nombre)
        .map(u => `<option value="${escapeHtml(u.nombre)}">${escapeHtml(u.nombre)} · ${escapeHtml(u.rol)}</option>`)
        .join('');

    wrapper.innerHTML = `
        <button type="button" class="rt-chat-toggle" id="rtChatToggle">
            <span class="rt-chat-dot offline" id="rtChatStatusDot"></span>
            <span>Chat</span>
            <small id="rtChatStatusText">conectando...</small>
        </button>

        <section class="rt-chat-panel">
            <header class="rt-chat-header">
                <div>
                    <strong>Chat general / privado</strong>
                    <span id="rtOnlineText">Sin conexión</span>
                </div>
                <button type="button" class="rt-chat-min" id="rtChatMin">—</button>
            </header>

            <div class="rt-chat-users">
                <label>Enviar a</label>
                <select id="rtChatTo">
                    <option value="">Chat general (todos)</option>
                    ${userOptions}
                </select>
            </div>

            <div class="rt-chat-messages" id="rtChatMessages"></div>

            <form id="rtChatForm" class="rt-chat-form">
                <input id="rtChatInput" type="text" placeholder="Escribir mensaje..." autocomplete="off" maxlength="600">
                <button type="submit">Enviar</button>
            </form>
        </section>
    `;

    document.body.appendChild(wrapper);

    document.getElementById('rtChatToggle').addEventListener('click', () => {
        wrapper.classList.toggle('collapsed');
        scrollChatAlFinal();
    });

    document.getElementById('rtChatMin').addEventListener('click', () => {
        wrapper.classList.add('collapsed');
    });

    document.getElementById('rtChatForm').addEventListener('submit', (ev) => {
        ev.preventDefault();
        enviarMensajeRealtime();
    });
}

function enviarMensajeRealtime() {
    const input = document.getElementById('rtChatInput');
    const select = document.getElementById('rtChatTo');

    if (!input || !realtimeSocket || realtimeSocket.readyState !== WebSocket.OPEN) {
        mostrarToastInterno('App Supervisores', 'Chat sin conexión. Reintentando...', null);
        return;
    }

    const message = input.value.trim();
    if (!message) return;

    realtimeSocket.send(JSON.stringify({
        type: 'chat_message',
        to: select ? select.value || null : null,
        message: message
    }));

    input.value = '';
}

function agregarMensajeChat(mensaje, animar) {
    if (!mensaje || !mensaje.id) return;

    const cont = document.getElementById('rtChatMessages');
    if (!cont) return;

    const existing = cont.querySelector(`[data-msg-id="${mensaje.id}"]`);
    if (existing) return;

    const actual = (window.APP_USER || {}).nombre;
    const propia = mensaje.remitente === actual;

    const bubble = document.createElement('div');
    bubble.className = `rt-bubble ${propia ? 'mine' : 'other'} ${animar ? 'new' : ''}`;
    bubble.dataset.msgId = mensaje.id;

    const destino = mensaje.destinatario ? ` → ${mensaje.destinatario}` : ' → Todos';
    const meta = `${mensaje.remitente}${destino} · ${mensaje.fecha || ''}`;

    bubble.innerHTML = `
        <div class="rt-bubble-meta">${escapeHtml(meta)}</div>
        <div class="rt-bubble-text">${escapeHtml(mensaje.mensaje || '')}</div>
    `;

    cont.appendChild(bubble);
    scrollChatAlFinal();
}

function scrollChatAlFinal() {
    const cont = document.getElementById('rtChatMessages');
    if (cont) cont.scrollTop = cont.scrollHeight;
}

function actualizarEstadoRealtime(online) {
    const dot = document.getElementById('rtChatStatusDot');
    const txt = document.getElementById('rtChatStatusText');
    const onlineText = document.getElementById('rtOnlineText');

    if (dot) {
        dot.classList.toggle('online', online);
        dot.classList.toggle('offline', !online);
    }

    if (txt) txt.textContent = online ? 'en línea' : 'offline';
    if (onlineText) onlineText.textContent = online ? 'Conectado' : 'Reconectando...';
}

async function cargarUsuariosChat() {
    try {
        const resp = await fetch('/api/usuarios', { cache: 'no-store' });
        if (!resp.ok) return;

        const data = await resp.json();
        if (!data.ok || !Array.isArray(data.usuarios)) return;

        realtimeOnlineUsers = data.usuarios.filter(u => u.online).map(u => u.nombre);
        actualizarUsuariosOnline();
    } catch (e) {}
}

function actualizarUsuariosOnline() {
    const onlineText = document.getElementById('rtOnlineText');
    if (onlineText) {
        const cantidad = realtimeOnlineUsers.length;
        onlineText.textContent = cantidad === 1 ? '1 usuario en línea' : `${cantidad} usuarios en línea`;
    }

    const select = document.getElementById('rtChatTo');
    if (!select) return;

    Array.from(select.options).forEach(opt => {
        if (!opt.value) return;
        const base = opt.textContent.replace(' 🟢', '').replace(' ⚪', '');
        opt.textContent = `${base}${realtimeOnlineUsers.includes(opt.value) ? ' 🟢' : ' ⚪'}`;
    });
}


/* ============================================================
   Observaciones y Dashboard en vivo
   ============================================================ */
function manejarNuevaObservacionRealtime(data) {
    const sucursal = data.sucursal || (data.observacion && data.observacion.sucursal) || '';
    const mensaje = data.message || `Nueva observación detectada en la sucursal ${sucursal}`;
    const notifId = data.notification_id || data.notificacion_id || data.id;

    // El emisor no debe escuchar ni ver toast por la acción que acaba de ejecutar.
    if (!eventoEsPropio(data) && !notificacionYaVista(notifId)) {
        marcarNotificacionVista(notifId);
        mostrarToastInterno(data.title || 'App Supervisores', mensaje, data.observacion_id);
        if (window.reproducirSonidoNotificacion) window.reproducirSonidoNotificacion();
    }

    actualizarDashboardEnVivo(data);
    insertarObservacionEnTabla(data.observacion || data);
}

function manejarEventoObservacionGenerico(data) {
    const notifId = data.notification_id || data.notificacion_id || data.id;

    if (!eventoEsPropio(data) && !notificacionYaVista(notifId)) {
        marcarNotificacionVista(notifId);
        mostrarToastInterno(data.title || 'App Supervisores', data.message || 'Nueva actualización', data.observacion_id);
        if (window.reproducirSonidoNotificacion) window.reproducirSonidoNotificacion();
    }

    if (window.location.pathname === '/dashboard') {
        actualizarDashboardEnVivo(data);
    }
}

function actualizarDashboardEnVivo(data) {
    if (window.location.pathname !== '/dashboard') return;

    incrementarMetrica('total', 1);

    const estado = data.estado || (data.observacion && data.observacion.estado) || '';
    const prioridad = data.prioridad || (data.observacion && data.observacion.prioridad) || '';

    if (estado === 'Pendiente') incrementarMetrica('pendientes', 1);
    if (estado === 'Resuelto') incrementarMetrica('resueltas', 1);
    if (estado === 'Pendiente' && ['Alta', 'Crítica'].includes(prioridad)) incrementarMetrica('criticas', 1);

    recalcularPorcentajeResolucion();
}

function incrementarMetrica(nombre, delta) {
    const card = document.querySelector(`[data-metric="${nombre}"]`);
    const value = card ? card.querySelector('p') : null;
    if (!value) return;

    const actual = parseInt(String(value.textContent || '0').replace(/[^0-9-]/g, ''), 10) || 0;
    value.textContent = String(actual + delta);
    card.classList.add('metric-live-pulse');
    setTimeout(() => card.classList.remove('metric-live-pulse'), 900);
}

function recalcularPorcentajeResolucion() {
    const total = obtenerMetricaNumerica('total');
    const resueltas = obtenerMetricaNumerica('resueltas');
    const card = document.querySelector('[data-metric="porcentaje"]');
    const value = card ? card.querySelector('p') : null;
    if (!value || total <= 0) return;
    value.textContent = `${((resueltas / total) * 100).toFixed(1)}%`;
}

function obtenerMetricaNumerica(nombre) {
    const card = document.querySelector(`[data-metric="${nombre}"]`);
    const value = card ? card.querySelector('p') : null;
    return value ? (parseInt(String(value.textContent || '0').replace(/[^0-9-]/g, ''), 10) || 0) : 0;
}

function insertarObservacionEnTabla(obs) {
    if (window.location.pathname !== '/observaciones') return;
    if (!obs || !obs.id) return;

    const tbody = document.getElementById('observacionesTableBody') || document.querySelector('#observacionesTable tbody');
    if (!tbody) return;

    if (tbody.querySelector(`[data-observacion-id="${obs.id}"]`)) return;

    const empty = tbody.querySelector('[data-empty-row="1"]');
    if (empty) empty.remove();

    const tr = document.createElement('tr');
    tr.dataset.observacionId = obs.id;
    tr.className = 'live-row-new';

    const prioridadClase = String(obs.prioridad || 'Media').toLowerCase().replace('í', 'i');
    const comentario = String(obs.comentario || '');
    const comentarioCorto = comentario.length > 120 ? `${comentario.slice(0, 120)}...` : comentario;
    const estado = obs.estado || 'Pendiente';
    const estadoClase = estado === 'Resuelto' ? 'resuelto' : 'pendiente';
    const actual = (window.APP_USER || {}).nombre;
    const rol = (window.APP_USER || {}).rol;
    const puedeEditar = rol === 'gerente' || obs.creado_por === actual;
    const puedeResolver = rol === 'gerente' && estado !== 'Resuelto';

    let acciones = `<a href="/chat/${encodeURIComponent(obs.id)}">Ver conversación / Responder</a><br>`;
    if (obs.evidencia_archivo) {
        const url = `/evidencias/${encodeURIComponent(obs.evidencia_archivo)}`;
        acciones += `<a class="evidence-link" href="${url}" data-evidence-src="${url}">Ver evidencia</a><br>`;
    }
    if (puedeEditar) acciones += `<a href="/editar/${encodeURIComponent(obs.id)}">Editar observación</a><br>`;
    if (puedeResolver) {
        acciones += `<form action="/resolver/${encodeURIComponent(obs.id)}" method="post" style="margin-top:6px;"><button type="submit">Marcar resuelto</button></form>`;
    }

    tr.innerHTML = `
        <td>${escapeHtml(obs.id)}</td>
        <td>${escapeHtml(obs.fecha_creacion || '')}</td>
        <td>${escapeHtml(obs.sucursal || '')}</td>
        <td>${escapeHtml(obs.supervisor || '')}</td>
        <td><span class="tag">${escapeHtml(obs.categoria || '')}</span></td>
        <td><span class="prioridad-${escapeHtml(prioridadClase)}">${escapeHtml(obs.prioridad || '')}</span></td>
        <td>${escapeHtml(comentarioCorto)}</td>
        <td class="${estadoClase}">${escapeHtml(estado)}</td>
        <td>${escapeHtml(obs.fecha_edicion || '')}</td>
        <td>${escapeHtml(obs.editado_por || '')}</td>
        <td>${acciones}</td>
    `;

    tbody.prepend(tr);
    inicializarEvidencias();
    setTimeout(() => tr.classList.remove('live-row-new'), 1800);
}

/* ============================================================
   Toast visual interno
   ============================================================ */
function mostrarToastInterno(title, body, observacionId) {
    let cont = document.getElementById('notifToastContainer');

    if (!cont) {
        cont = document.createElement('div');
        cont.id = 'notifToastContainer';
        // No usamos bottom-0 porque se superpone con el chat flotante.
        cont.className = 'toast-container position-fixed p-3 notif-toast-container';
        document.body.appendChild(cont);
    }

    const toastEl = document.createElement('div');
    toastEl.className = 'toast notif-toast bootstrap-live-toast';
    toastEl.setAttribute('role', 'alert');
    toastEl.setAttribute('aria-live', 'assertive');
    toastEl.setAttribute('aria-atomic', 'true');
    toastEl.innerHTML = `
        <div class="toast-header notif-toast-title-wrap">
            <strong class="me-auto">${escapeHtml(title)}</strong>
            <small>Ahora</small>
            <button type="button" class="btn-close ms-2 mb-1" data-bs-dismiss="toast" aria-label="Cerrar"></button>
        </div>
        <div class="toast-body notif-toast-body">${escapeHtml(body)}</div>
    `;

    toastEl.addEventListener('click', function (ev) {
        if (ev.target && ev.target.classList.contains('btn-close')) return;
        if (observacionId) window.location.href = `/chat/${observacionId}`;
    });

    cont.appendChild(toastEl);

    if (typeof bootstrap !== 'undefined' && bootstrap.Toast) {
        const toast = new bootstrap.Toast(toastEl, { delay: 8000, autohide: true });
        toast.show();
        toastEl.addEventListener('hidden.bs.toast', () => toastEl.remove());
    } else {
        toastEl.classList.add('show');
        setTimeout(() => toastEl.remove(), 8000);
    }
}

function escapeHtml(str) {
    return String(str || '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}
