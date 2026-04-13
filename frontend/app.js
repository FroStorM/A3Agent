const { createApp, ref, computed, onMounted, nextTick, watch } = Vue;

createApp({
    setup() {
        const sidebarOpen = ref(window.innerWidth > 768);
        const inputMessage = ref('');
        const messages = ref([]);
        const isTyping = ref(false);
        const status = ref({ llm_name: '', is_running: false });
        const activeModal = ref('');
        const todoContent = ref('');
        const sopFiles = ref([]);
        const selectedSop = ref('');
        const sopContent = ref('');
        const scheduleFiles = ref({ pending: [], running: [], done: [] });
        const selectedScheduleBucket = ref('');
        const selectedScheduleName = ref('');
        const scheduleContent = ref('');
        const llmConfigs = ref([]);
        const authReady = ref(false);
        const currentUser = ref(null);
        const authMode = ref('login');
        const loginUsername = ref('');
        const loginPassword = ref('');
        const loginBusy = ref(false);
        const authError = ref('');
        const authNotice = ref('');
        const registerUsername = ref('');
        const registerEmail = ref('');
        const registerPassword = ref('');
        const registerConfirmPassword = ref('');
        const registerBusy = ref(false);
        const adminUsers = ref([]);
        const selectedAdminUsername = ref('');
        const adminScope = ref('memory');
        const adminFiles = ref([]);
        const selectedAdminFilePath = ref('');
        const adminFileContent = ref('');
        const adminFileEditMode = ref(false);
        const adminFileDraft = ref('');
        const adminBusy = ref(false);
        const adminError = ref('');
        const adminNotice = ref('');
        const copyTargetUsername = ref('');
        const copyTargetPath = ref('');
        const adminUserSearch = ref('');
        const adminRoleFilter = ref('all');
        const adminStatusFilter = ref('all');
        const adminSelectedTargets = ref([]);
        const batchCopyPath = ref('');
        const adminUploadPath = ref('');
        const adminUploadFileName = ref('');
        const adminCreatePath = ref('');
        const adminCreateKind = ref('file');
        const adminRenamePath = ref('');
        const auditLogs = ref([]);
        const auditActionFilter = ref('');
        const auditTargetFilter = ref('');
        const adminLimitParallel = ref(1);
        const adminLimitPrompt = ref(20000);
        const adminLimitUploadMb = ref(10);
        const createUsername = ref('');
        const createPassword = ref('');
        const createIsAdmin = ref(false);
        const adminResetPassword = ref('');
        const passwordOld = ref('');
        const passwordNew = ref('');
        const passwordConfirm = ref('');
        const passwordBusy = ref(false);
        const passwordError = ref('');
        const passwordNotice = ref('');
        const keyEditorOpen = ref(false);
        const editingConfigId = ref('');
        const editType = ref('oai');
        const editApiBase = ref('');
        const editModel = ref('');
        const editApiKey = ref('');
        const keyEditorError = ref('');
        const keyEditorNotice = ref('');
        const keyEditorTesting = ref(false);
        const keyEditorSaving = ref(false);
        const keyEditorTestOk = ref(false);
        const keyEditorTestFingerprint = ref('');
        const renderLimit = ref(120);
        const stickToBottom = ref(true);
        let loadingMoreHistory = false;
        const renderStep = 60;
        const renderMax = 900;
        const foldThreshold = 20000;
        const previewChars = 6000;
        const hiddenCount = computed(() => Math.max(0, messages.value.length - renderLimit.value));
        const visibleMessages = computed(() => {
            const start = Math.max(0, messages.value.length - renderLimit.value);
            return messages.value.slice(start);
        });

        const apiReady = ref(false);
        let bootstrapLoaded = false;
        const isAdmin = computed(() => !!(currentUser.value && currentUser.value.is_admin));
        const selectedAdminUser = computed(() => {
            if (!selectedAdminUsername.value) return null;
            return adminUsers.value.find((user) => user.username === selectedAdminUsername.value) || null;
        });
        const filteredAdminUsers = computed(() => {
            const keyword = (adminUserSearch.value || '').trim().toLowerCase();
            return adminUsers.value.filter((user) => {
                if (keyword && !String(user.username || '').toLowerCase().includes(keyword)) return false;
                if (adminRoleFilter.value === 'admin' && !user.is_admin) return false;
                if (adminRoleFilter.value === 'member' && user.is_admin) return false;
                if (adminStatusFilter.value === 'active' && !user.is_active) return false;
                if (adminStatusFilter.value === 'disabled' && user.is_active) return false;
                return true;
            });
        });
        const allFilteredTargetsSelected = computed(() => {
            const candidates = filteredAdminUsers.value
                .map((user) => user.username)
                .filter((username) => username !== selectedAdminUsername.value);
            if (!candidates.length) return false;
            return candidates.every((username) => adminSelectedTargets.value.includes(username));
        });
        const syncSelectedAdminLimits = () => {
            const user = selectedAdminUser.value;
            if (!user) return;
            adminLimitParallel.value = Number(user.max_parallel_runs || 1);
            adminLimitPrompt.value = Number(user.max_prompt_chars || 20000);
            adminLimitUploadMb.value = Math.max(1, Math.round(Number(user.max_upload_bytes || 10485760) / (1024 * 1024)));
        };

        const getPrefersDark = () => {
            try { return !!(window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches); } catch (e) { return false; }
        };

        const applyTheme = (mode) => {
            const html = document.documentElement;
            const isDark = mode === 'dark' || (mode === 'system' && getPrefersDark());
            if (isDark) {
                html.classList.add('dark');
            } else {
                html.classList.remove('dark');
            }
            html.style.colorScheme = isDark ? 'dark' : 'light';
            try { localStorage.setItem('ga_theme', mode); } catch (e) {}
        };

        const getStoredMode = () => {
            const v = (() => { try { return localStorage.getItem('ga_theme'); } catch (e) { return null; } })();
            return (v === 'light' || v === 'dark' || v === 'system') ? v : 'light';
        };

        const nextMode = (v) => v === 'system' ? 'light' : (v === 'light' ? 'dark' : 'system');

        const getModeLabel = (v) => {
            if (v === 'light') return '主题：浅色（点击切换）';
            if (v === 'dark') return '主题：深色（点击切换）';
            return '主题：跟随系统（点击切换）';
        };

        const getModeIcon = (v) => {
            if (v === 'light') return 'sun';
            if (v === 'dark') return 'moon';
            return 'monitor';
        };

        const renderThemeButton = () => {
            const mode = getStoredMode();
            const btn = document.getElementById('themeToggle');
            if (btn) {
                btn.title = getModeLabel(mode);
                btn.innerHTML = '<i data-lucide="' + getModeIcon(mode) + '" class="w-4 h-4"></i>';
                if (window.lucide) lucide.createIcons();
            }
        };

        const toggleTheme = () => {
            const current = getStoredMode();
            const next = nextMode(current);
            applyTheme(next);
            renderThemeButton();
        };
        window.toggleTheme = toggleTheme;
        renderThemeButton();

        const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
        let floatingStateHint = '';
        let floatingStateHintUntil = 0;
        const streamDebugEvents = ref([]);
        const submissionNotice = ref('');
        const submitInFlight = ref(false);
        const pendingSubmissions = new Map();
        let currentSubmitAbortController = null;
        const pushStreamDebug = (kind, detail = {}) => {
            const entry = {
                ts: new Date().toLocaleTimeString(),
                kind,
                ...detail,
            };
            streamDebugEvents.value.unshift(entry);
            if (streamDebugEvents.value.length > 40) {
                streamDebugEvents.value.length = 40;
            }
            try {
                console.debug('[StreamDebug]', entry);
            } catch {}
        };
        if (typeof window !== 'undefined') {
            window.__A3_STREAM_DEBUG__ = streamDebugEvents;
        }

        const looksLikeHumanRequest = (text) => {
            const s = String(text || '');
            if (!s) return false;
            return /Waiting for your answer/i.test(s)
                || /请选择/.test(s)
                || /请提供输入/.test(s)
                || /请回复/.test(s)
                || /需要用户/.test(s)
                || /HUMAN_INTERVENTION/.test(s)
                || /INTERRUPT/.test(s);
        };

        const setFloatingStateHint = (state, ttlMs = 0) => {
            floatingStateHint = state || '';
            floatingStateHintUntil = ttlMs > 0 ? (Date.now() + ttlMs) : 0;
        };

        const getFloatingStateHint = () => {
            if (!floatingStateHint) return '';
            if (floatingStateHintUntil && Date.now() > floatingStateHintUntil) {
                floatingStateHint = '';
                floatingStateHintUntil = 0;
                return '';
            }
            return floatingStateHint;
        };

        // Load Lucide icons
        onMounted(() => {
            if (window.lucide) lucide.createIcons();

            // Theme toggle button
            const btn = document.getElementById('themeToggle');
            if (btn) btn.addEventListener('click', toggleTheme);

            initializeSession();
            setInterval(async () => {
                if (!currentUser.value) return;
                const ok = await fetchStatus();
                if (ok && !bootstrapLoaded) {
                    await ensureBackendDataLoaded();
                }
            }, 5000);
            
            // Auto-resize textarea
            const textarea = document.querySelector('textarea');
            if (textarea) {
                textarea.addEventListener('input', function() {
                    this.style.height = 'auto';
                    this.style.height = (this.scrollHeight) + 'px';
                    if (this.value === '') this.style.height = '3.5rem';
                });
            }
            
            // Handle window resize for sidebar
            window.addEventListener('resize', () => {
                if (window.innerWidth > 768) {
                    sidebarOpen.value = true;
                } else {
                    sidebarOpen.value = false;
                }
            });
            
        });

        // Watch sidebar state to re-render icons if needed
        watch(sidebarOpen, () => {
            nextTick(() => {
                if (window.lucide) lucide.createIcons();
            });
        });

        // Global Event Source for Stream
        let eventSource = null;
        let sseReconnectTimer = null;
        const runStates = new Map();
        let activeStreamRuns = 0;
        const streamViewMax = 60000;
        const streamTailMax = 16000;
        let scrollScheduled = false;

        const escapeHtml = (input) => {
            const s = String(input ?? '');
            return s
                .replaceAll('&', '&amp;')
                .replaceAll('<', '&lt;')
                .replaceAll('>', '&gt;')
                .replaceAll('"', '&quot;')
                .replaceAll("'", '&#39;');
        };

        const safeRenderMarkdown = (text) => {
            const raw = String(text ?? '');
            if (!raw) return '';
            if (raw.length >= 120000) {
                return `<pre class="whitespace-pre-wrap break-words">${escapeHtml(raw)}</pre>`;
            }
            try {
                return marked.parse(raw);
            } catch (e) {
                return `<pre class="whitespace-pre-wrap break-words">${escapeHtml(raw)}</pre>`;
            }
        };

        const finalizeMessage = (msg) => {
            const raw = String(msg?.content ?? '');
            msg.isFolded = raw.length > foldThreshold;
            msg.expanded = !msg.isFolded;
            msg.preview = msg.isFolded ? raw.slice(0, previewChars) : '';
            msg.html = msg.expanded ? safeRenderMarkdown(raw) : '';
        };

        const makeMessage = (role, content, extra = {}) => {
            const msg = {
                id: (typeof crypto !== 'undefined' && crypto.randomUUID) ? crypto.randomUUID() : `${Date.now()}_${Math.random().toString(16).slice(2)}`,
                role,
                content: String(content ?? ''),
                html: '',
                streaming: !!extra.streaming,
                timestamp: extra.timestamp || new Date().toLocaleTimeString(),
                isFolded: false,
                expanded: true,
                preview: ''
            };
            if (extra.source) msg.source = extra.source;
            if (extra.run_id) msg.run_id = extra.run_id;
            if (msg.streaming) {
                msg.parts = [];
                msg.totalLen = 0;
                msg.tail = '';
            }
            if (!msg.streaming) finalizeMessage(msg);
            return msg;
        };

        const expandMessage = async (msg) => {
            if (!msg || !msg.isFolded) return;
            msg.expanded = true;
            if (!msg.html) msg.html = safeRenderMarkdown(msg.content);
            await nextTick();
        };

        const loadMoreHistory = async (containerEl = null) => {
            if (loadingMoreHistory || hiddenCount.value <= 0) return;
            loadingMoreHistory = true;
            const container = containerEl || document.getElementById('chat-container');
            const beforeHeight = container ? container.scrollHeight : 0;
            const beforeTop = container ? container.scrollTop : 0;
            renderLimit.value = Math.min(messages.value.length, Math.min(renderMax, renderLimit.value + renderStep));
            await nextTick();
            if (container) {
                const afterHeight = container.scrollHeight;
                container.scrollTop = beforeTop + (afterHeight - beforeHeight);
            }
            loadingMoreHistory = false;
        };

        const onChatScroll = async (event) => {
            const el = event?.target;
            if (!el) return;
            const distance = el.scrollHeight - (el.scrollTop + el.clientHeight);
            stickToBottom.value = distance < 120;
            if (el.scrollTop < 80 && hiddenCount.value > 0) {
                await loadMoreHistory(el);
            }
        };

        const jumpToLatest = async () => {
            if (hiddenCount.value > 0) renderLimit.value = Math.min(messages.value.length, Math.max(renderLimit.value, 120));
            stickToBottom.value = true;
            await nextTick();
            const container = document.getElementById('chat-container');
            if (container) container.scrollTop = container.scrollHeight;
        };
        
        const initStream = async () => {
            if (eventSource) eventSource.close();
            if (sseReconnectTimer) {
                clearTimeout(sseReconnectTimer);
                sseReconnectTimer = null;
            }

            let streamUrl = '/api/stream';
            try {
                if (typeof window.__GA_RESOLVE_API_URL__ === 'function') {
                    streamUrl = await window.__GA_RESOLVE_API_URL__(streamUrl);
                }
            } catch (e) {
                console.warn('resolve stream url failed', e);
            }

            eventSource = new EventSource(streamUrl);
            pushStreamDebug('sse-open', { readyState: eventSource.readyState });
            eventSource.onopen = () => {
                pushStreamDebug('sse-onopen', { readyState: eventSource.readyState });
            };
            
            eventSource.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    const runId = String(data.run_id || '__default__');
                    const requestId = String(data.request_id || '');
                    pushStreamDebug('sse-message', {
                        type: data.type || '',
                        state: data.state || '',
                        run_id: runId,
                        request_id: requestId,
                        content_len: typeof data.content === 'string' ? data.content.length : 0,
                    });

                    const updateTypingState = () => {
                        isTyping.value = runStates.size > 0;
                    };

                    const flushRun = (rid) => {
                        const st = runStates.get(rid);
                        if (!st) return;
                        const msg = messages.value[st.assistantIndex];
                        if (!msg || msg.role !== 'assistant') return;
                        const buf = st.buffer;
                        if (!buf) return;
                        st.buffer = '';
                        if (Array.isArray(msg.parts)) msg.parts.push(buf);
                        msg.totalLen = (msg.totalLen || 0) + buf.length;
                        if (msg.totalLen <= streamViewMax) {
                            msg.content += buf;
                        } else {
                            msg.tail = (String(msg.tail || '') + buf).slice(-streamTailMax);
                            msg.content = `【输出过长，流式仅显示末尾 ${streamTailMax} 字】\n` + msg.tail;
                        }
                        pushStreamDebug('flush-run', {
                            run_id: rid,
                            flushed_len: buf.length,
                            total_len: msg.totalLen,
                            rendered_len: msg.content.length,
                        });
                        scrollToBottom();
                    };

                    const scheduleFlush = (rid) => {
                        const st = runStates.get(rid);
                        if (!st) return;
                        if (st.flushTimer) return;
                        st.flushTimer = setTimeout(() => {
                            st.flushTimer = null;
                            flushRun(rid);
                        }, 50);
                    };
                    
                    if (data.type === 'message') {
                        // This is a prompt (from user or autonomous)
                        pushStreamDebug('message', {
                            run_id: runId,
                            request_id: requestId,
                            source: data.source || '',
                            prompt_len: typeof data.content === 'string' ? data.content.length : 0,
                        });
                        messages.value.push(makeMessage('user', data.content, {
                            timestamp: data.timestamp || new Date().toLocaleTimeString(),
                            source: data.source,
                            run_id: runId
                        }));
                        const pending = requestId ? pendingSubmissions.get(requestId) : null;
                        if (pending) {
                            pending.confirmed = true;
                            pendingSubmissions.set(requestId, pending);
                            // 移除状态提示
                            pushStreamDebug('submit-acked', {
                                run_id: runId,
                                request_id: requestId,
                                prompt_len: pending.prompt_len,
                            });
                        }
                        scrollToBottom();
                        
                        // Prepare assistant message placeholder
                        messages.value.push(makeMessage('assistant', '', { streaming: true, run_id: runId }));
                        runStates.set(runId, { assistantIndex: messages.value.length - 1, buffer: '', flushTimer: null });
                        updateTypingState();
                    } else if (data.type === 'state') {
                        if (data.state === 'need-user') {
                            status.value.needs_human_input = true;
                            status.value.is_running = false;
                            setFloatingStateHint('need-user');
                            emitFloatingStatus(status.value, false, 'need-user');
                        } else if (data.state === 'running') {
                            status.value.is_running = true;
                            status.value.needs_human_input = false;
                            setFloatingStateHint('running', 30000);
                            emitFloatingStatus(status.value, true, 'running');
                        } else if (data.state === 'idle') {
                            status.value.is_running = false;
                            status.value.needs_human_input = false;
                            if (!status.value.needs_human_input) {
                                setFloatingStateHint('idle');
                                emitFloatingStatus(status.value, false, 'idle');
                            }
                        } else if (data.state === 'error') {
                            emitFloatingStatus(status.value, false, 'error');
                        }
                    } else if (data.type === 'chunk') {
                        const st = runStates.get(runId);
                        if (!st) return;
                        const msg = messages.value[st.assistantIndex];
                        if (msg && msg.role === 'assistant') {
                            st.buffer += String(data.content ?? '');
                        pushStreamDebug('chunk-buffer', {
                            run_id: runId,
                            request_id: requestId,
                            chunk_len: String(data.content ?? '').length,
                            buffered_len: st.buffer.length,
                            msg_len: msg.content.length,
                        });
                            scheduleFlush(runId);
                        }
                    } else if (data.type === 'done') {
                        const st = runStates.get(runId);
                        pushStreamDebug('done-recv', {
                            run_id: runId,
                            request_id: requestId,
                            has_state: !!st,
                            active_runs: activeStreamRuns,
                            content_len: typeof data.content === 'string' ? data.content.length : 0,
                        });
                        if (!st) {
                            activeStreamRuns = Math.max(0, activeStreamRuns - 1);
                            if (looksLikeHumanRequest(data.content)) {
                                status.value.needs_human_input = true;
                                setFloatingStateHint('need-user');
                                emitFloatingStatus(status.value, false, 'need-user');
                            } else if (activeStreamRuns <= 0) {
                                setFloatingStateHint('idle');
                                emitFloatingStatus(status.value, false, 'idle');
                            } else {
                                emitFloatingStatus(status.value, activeStreamRuns > 0);
                            }
                            updateTypingState();
                            return;
                        }
                        if (st.flushTimer) {
                            clearTimeout(st.flushTimer);
                            st.flushTimer = null;
                        }
                        flushRun(runId);
                        const msg = messages.value[st.assistantIndex];
                        if (msg && msg.role === 'assistant') {
                            const full = (data.content !== undefined && data.content !== null && String(data.content) !== '')
                                ? String(data.content)
                                : (Array.isArray(msg.parts) ? msg.parts.join('') : msg.content);
                            msg.content = full;
                            msg.streaming = false;
                            finalizeMessage(msg);
                            pushStreamDebug('done-finalize', {
                                run_id: runId,
                                request_id: requestId,
                                full_len: full.length,
                                is_human_like: looksLikeHumanRequest(full),
                            });
                            if (looksLikeHumanRequest(full)) {
                                status.value.needs_human_input = true;
                                status.value.is_running = false;
                                setFloatingStateHint('need-user');
                            } else if (activeStreamRuns <= 1) {
                                status.value.needs_human_input = false;
                                setFloatingStateHint('idle');
                            }
                        }
                        runStates.delete(runId);
                        activeStreamRuns = Math.max(0, activeStreamRuns - 1);
                        if (requestId && pendingSubmissions.has(requestId)) {
                            pendingSubmissions.delete(requestId);
                        } else {
                            pendingSubmissions.delete(runId);
                        }
                        if (pendingSubmissions.size === 0 && !submitInFlight.value) {
                            submissionNotice.value = '';
                        }
                        if (looksLikeHumanRequest(data.content) || status.value.needs_human_input) {
                            emitFloatingStatus(status.value, false, 'need-user');
                        } else if (activeStreamRuns > 0) {
                            emitFloatingStatus(status.value, true, 'running');
                        } else {
                            status.value.needs_human_input = false;
                            emitFloatingStatus(status.value, false, 'idle');
                        }
                        updateTypingState();
                        scrollToBottom();
                    } else if (data.type === 'start') {
                        activeStreamRuns += 1;
                        status.value.needs_human_input = false;
                        setFloatingStateHint('running', 30000);
                        pushStreamDebug('start-recv', { run_id: runId, request_id: requestId, active_runs: activeStreamRuns });
                        emitFloatingStatus(status.value, true);
                        updateTypingState();
                    }
                } catch (e) {
                    pushStreamDebug('sse-parse-error', { error: String(e && e.message ? e.message : e) });
                    console.error('Error parsing SSE:', e);
                }
            };
            
            eventSource.onerror = (e) => {
                pushStreamDebug('sse-error', {
                    readyState: eventSource ? eventSource.readyState : -1,
                    active_runs: activeStreamRuns,
                });
                if (!sseReconnectTimer) {
                    eventSource.close();
                    sseReconnectTimer = setTimeout(() => {
                        sseReconnectTimer = null;
                        initStream();
                    }, 3000);
                }
            };
        };

        const emitFloatingStatus = (data, overrideIsRunning = null, explicitState = null) => {
            try {
                const tauri = window.__TAURI__;
                if (!tauri || !tauri.event || typeof tauri.event.emit !== 'function') return;
                const backendRunning = !!(data && data.is_running);
                const needsHuman = !!(data && data.needs_human_input);
                const effectiveRunning = overrideIsRunning === null
                    ? (backendRunning || activeStreamRuns > 0)
                    : !!overrideIsRunning;
                const hintedState = getFloatingStateHint();
                const resolvedState = explicitState
                    || ((data && data.agent_init_error) ? 'error' : '')
                    || (effectiveRunning ? 'running' : '')
                    || (needsHuman ? 'need-user' : '')
                    || (hintedState === 'running' ? 'running' : '')
                    || (hintedState === 'idle' ? 'idle' : '')
                    || 'idle';
                tauri.event.emit('ga-status', {
                    is_running: effectiveRunning,
                    needs_human_input: needsHuman,
                    agent_init_error: (data && data.agent_init_error) ? String(data.agent_init_error) : '',
                    state: resolvedState
                });
                pushStreamDebug('emit-status', {
                    state: resolvedState,
                    is_running: effectiveRunning,
                    needs_human_input: needsHuman,
                });
            } catch {}
        };

        const fetchStatus = async () => {
            if (!currentUser.value) return false;
            try {
                const res = await fetch('/api/status');
                if (res.ok) {
                    const data = await res.json();
                    status.value = data;
                    apiReady.value = true;
                    emitFloatingStatus(data);
                    return true;
                }
                apiReady.value = false;
                return false;
            } catch (e) {
                console.error('Failed to fetch status:', e);
                apiReady.value = false;
                return false;
            }
        };

        const fetchAuthMe = async () => {
            try {
                const res = await fetch('/api/auth/me');
                if (!res.ok) {
                    currentUser.value = null;
                    authReady.value = true;
                    return false;
                }
                const data = await res.json();
                currentUser.value = data && data.authenticated ? data.user : null;
                authReady.value = true;
                return !!currentUser.value;
            } catch (e) {
                console.error('Fetch auth me failed:', e);
                currentUser.value = null;
                authReady.value = true;
                return false;
            }
        };

        const initializeSession = async () => {
            const ok = await fetchAuthMe();
            if (!ok) {
                apiReady.value = false;
                bootstrapLoaded = false;
                if (eventSource) {
                    eventSource.close();
                    eventSource = null;
                }
                return;
            }
            await initStream();
            await ensureBackendDataLoaded();
            if (isAdmin.value) {
                await fetchAdminUsers();
            }
        };

        const login = async () => {
            try {
                loginBusy.value = true;
                authError.value = '';
                authNotice.value = '';
                const res = await fetch('/api/auth/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        username: loginUsername.value || '',
                        password: loginPassword.value || '',
                    }),
                });
                const data = await res.json().catch(() => ({}));
                if (!res.ok || !data || data.error) {
                    authError.value = (data && data.error) ? data.error : '登录失败';
                    return false;
                }
                loginPassword.value = '';
                await initializeSession();
                return true;
            } catch (e) {
                authError.value = String(e && e.message ? e.message : e);
                return false;
            } finally {
                loginBusy.value = false;
            }
        };

        const register = async () => {
            try {
                registerBusy.value = true;
                authError.value = '';
                authNotice.value = '';
                const res = await fetch('/api/auth/register', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        username: registerUsername.value || '',
                        email: registerEmail.value || '',
                        password: registerPassword.value || '',
                        confirm_password: registerConfirmPassword.value || '',
                    }),
                });
                const data = await res.json().catch(() => ({}));
                if (!res.ok || !data || data.error) {
                    authError.value = (data && data.error) ? data.error : '注册失败';
                    return false;
                }
                authNotice.value = '注册成功，已自动登录';
                registerPassword.value = '';
                registerConfirmPassword.value = '';
                await initializeSession();
                return true;
            } catch (e) {
                authError.value = String(e && e.message ? e.message : e);
                return false;
            } finally {
                registerBusy.value = false;
            }
        };

        const logout = async () => {
            try {
                await fetch('/api/auth/logout', { method: 'POST' });
            } catch (e) {
                console.error('Logout failed:', e);
            }
            currentUser.value = null;
            authReady.value = true;
            apiReady.value = false;
            bootstrapLoaded = false;
            authNotice.value = '';
            activeModal.value = '';
            adminUsers.value = [];
            adminFiles.value = [];
            adminFileContent.value = '';
            selectedAdminFilePath.value = '';
            adminResetPassword.value = '';
            passwordOld.value = '';
            passwordNew.value = '';
            passwordConfirm.value = '';
            passwordError.value = '';
            passwordNotice.value = '';
            if (eventSource) {
                eventSource.close();
                eventSource = null;
            }
        };

        const ensureBackendDataLoaded = async (attempts = 20, intervalMs = 800) => {
            if (!currentUser.value) return false;
            for (let i = 0; i < attempts; i += 1) {
                const ok = await fetchStatus();
                if (ok) {
                    await fetchLlmConfigs();
                    await fetchSopList();
                    bootstrapLoaded = true;
                    return true;
                }
                await sleep(intervalMs);
            }
            return false;
        };

        const reloadAgent = async () => {
            try {
                const res = await fetch('/api/control', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ action: 'reload_agent' })
                });
                const data = await res.json().catch(() => ({}));
                if (!res.ok || (data && data.error)) {
                    return { ok: false, error: (data && data.error) ? data.error : 'reload failed' };
                }
                const ok = await fetchStatus();
                if (ok && status.value && status.value.agent_init_error) {
                    return { ok: false, error: status.value.agent_init_error };
                }
                return { ok: true };
            } catch (e) {
                console.error('Reload agent failed:', e);
                return { ok: false, error: String(e && e.message ? e.message : e) };
            }
        };

        const openKeyEditorWithRetry = async (configId, timeoutMs = 4000, intervalMs = 300) => {
            if (!configId) return;
            const start = Date.now();
            while (Date.now() - start < timeoutMs) {
                await fetchLlmConfigs();
                const cfg = llmConfigs.value.find((c) => c.id === configId);
                if (cfg) {
                    editingConfigId.value = cfg.id;
                    editType.value = (cfg.type === 'claude') ? 'claude' : 'oai';
                    editApiBase.value = cfg.apibase || '';
                    editModel.value = cfg.model || '';
                    editApiKey.value = '';
                    keyEditorError.value = '';
                    keyEditorNotice.value = '';
                    keyEditorOpen.value = true;
                    await nextTick();
                    const el = document.getElementById('ga-key-editor');
                    if (el && typeof el.scrollIntoView === 'function') {
                        el.scrollIntoView({ block: 'nearest' });
                    }
                    if (window.lucide) lucide.createIcons();
                    return true;
                }
                await new Promise((r) => setTimeout(r, intervalMs));
            }
            keyEditorOpen.value = true;
            editingConfigId.value = configId;
            return false;
        };

        const scrollToBottom = () => {
            if (!stickToBottom.value) return;
            if (scrollScheduled) return;
            scrollScheduled = true;
            nextTick(() => {
                requestAnimationFrame(() => {
                    scrollScheduled = false;
                    const container = document.getElementById('chat-container');
                    if (container) container.scrollTop = container.scrollHeight;
                });
            });
        };

        const sendMessage = async () => {
            if (!currentUser.value) {
                authError.value = '请先登录';
                return;
            }
            if (!inputMessage.value.trim() || isTyping.value) return;

            const prompt = inputMessage.value;
            const requestId = (typeof crypto !== 'undefined' && crypto.randomUUID)
                ? crypto.randomUUID()
                : `${Date.now()}_${Math.random().toString(16).slice(2)}`;
            if (currentSubmitAbortController) {
                try { currentSubmitAbortController.abort(); } catch {}
            }
            currentSubmitAbortController = new AbortController();
            submitInFlight.value = true;
            submissionNotice.value = '正在提交到后端...';
            pushStreamDebug('send-start', {
                request_id: requestId,
                prompt_len: prompt.length,
                run_states: runStates.size,
                active_runs: activeStreamRuns,
            });

            // Reset textarea height immediately, but keep the text until the backend acks it.
            const textarea = document.querySelector('textarea');
            if (textarea) textarea.style.height = '3.5rem';

            try {
                const response = await fetch('/api/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ prompt, request_id: requestId }),
                    signal: currentSubmitAbortController.signal
                });

                const data = await response.json().catch(() => ({}));
                if (!response.ok || (data && data.error)) throw new Error((data && data.error) ? data.error : 'Network response was not ok');

                const runId = String(data.run_id || '');
                pendingSubmissions.set(requestId, {
                    request_id: requestId,
                    run_id: runId,
                    prompt_len: prompt.length,
                    confirmed: false,
                    startedAt: Date.now(),
                });
                // 移除状态提示
                pushStreamDebug('send-queued', {
                    request_id: requestId,
                    run_id: runId,
                    status: response.status,
                });

                inputMessage.value = '';
                submitInFlight.value = false;
                currentSubmitAbortController = null;
                isTyping.value = true;
                status.value.is_running = true;
                status.value.needs_human_input = false;
                setFloatingStateHint('running', 30000);
                emitFloatingStatus(status.value, true, 'running');
            } catch (e) {
                const aborted = e && (e.name === 'AbortError' || String(e).includes('aborted'));
                console.error('Send failed:', e);
                submitInFlight.value = false;
                currentSubmitAbortController = null;
                submissionNotice.value = aborted ? '已放弃当前等待' : '提交失败：' + e.message;
                status.value.is_running = false;
                setFloatingStateHint('idle');
                emitFloatingStatus(status.value, false, 'error');
                isTyping.value = false;
            }
        };

        const renderMarkdown = (text) => {
            return safeRenderMarkdown(text || '');
        };

        const copyToClipboard = (text) => {
            navigator.clipboard.writeText(text).then(() => {
            });
        };

        const switchLLM = async (index = null) => {
            try {
                const body = { action: 'switch_llm' };
                if (index !== null) body.index = index;
                
                await fetch('/api/control', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body)
                });
                fetchStatus();
            } catch (e) {
                console.error('Switch LLM failed:', e);
            }
        };

        const openModal = async (name) => {
            if (!currentUser.value) {
                authError.value = '请先登录';
                return;
            }
            activeModal.value = name;
            try {
                if (!apiReady.value) {
                    await ensureBackendDataLoaded(6, 500);
                }
                if (name === 'model') {
                    keyEditorOpen.value = false;
                    editingConfigId.value = '';
                    editApiKey.value = '';
                    await fetchStatus();
                    await fetchLlmConfigs();
                }
                if (name === 'todo') await fetchToDo();
                if (name === 'sop') await fetchSopList();
                if (name === 'schedule') await refreshScheduleList();
                if (name === 'password') {
                    passwordOld.value = '';
                    passwordNew.value = '';
                    passwordConfirm.value = '';
                    passwordError.value = '';
                    passwordNotice.value = '';
                }
                if (name === 'admin') {
                    await fetchAdminUsers();
                    if (selectedAdminUsername.value) {
                        await fetchAdminFiles();
                    }
                    await fetchAuditLogs();
                }
            } finally {
                nextTick(() => {
                    if (window.lucide) lucide.createIcons();
                });
            }
        };

        const closeModal = () => {
            activeModal.value = '';
            keyEditorOpen.value = false;
        };

        const fetchLlmConfigs = async () => {
            if (!currentUser.value) return false;
            try {
                const res = await fetch('/api/llm_configs');
                if (!res.ok) return false;
                const data = await res.json();
                llmConfigs.value = data.configs || [];
                return true;
            } catch (e) {
                console.error('Fetch llm configs failed:', e);
                return false;
            }
        };

        const editingConfig = computed(() => {
            if (!editingConfigId.value) return null;
            return llmConfigs.value.find((c) => c.id === editingConfigId.value) || null;
        });

        const editingHasKey = computed(() => {
            return !!(editingConfig.value && editingConfig.value.has_key);
        });

        const editingKeyLast4 = computed(() => {
            return (editingConfig.value && editingConfig.value.key_last4) ? editingConfig.value.key_last4 : '';
        });

        const editingTitle = computed(() => {
            if (editingConfigId.value) return `配置：${editingConfigId.value}`;
            return '新增模型';
        });

        const keyEditorBusy = computed(() => {
            return keyEditorTesting.value || keyEditorSaving.value;
        });

        const makeKeyEditorFingerprint = () => {
            const keyLen = String(editApiKey.value || '').trim().length;
            return JSON.stringify({
                id: String(editingConfigId.value || ''),
                type: String(editType.value || ''),
                apibase: String(editApiBase.value || '').trim(),
                model: String(editModel.value || '').trim(),
                apikey_len: keyLen
            });
        };

        watch([editType, editApiBase, editModel, editApiKey, editingConfigId], () => {
            keyEditorTestOk.value = false;
            keyEditorTestFingerprint.value = '';
            keyEditorNotice.value = '';
        });

        const openKeyEditor = async (configId) => {
            if (!llmConfigs.value.length) await fetchLlmConfigs();
            const cfg = llmConfigs.value.find((c) => c.id === configId);
            if (!cfg) return;
            editingConfigId.value = cfg.id;
            editType.value = (cfg.type === 'claude') ? 'claude' : 'oai';
            editApiBase.value = cfg.apibase || '';
            editModel.value = cfg.model || '';
            editApiKey.value = '';
            keyEditorError.value = '';
            keyEditorNotice.value = '';
            keyEditorOpen.value = true;
            nextTick(() => {
                if (window.lucide) lucide.createIcons();
            });
        };

        const startNewModel = () => {
            editingConfigId.value = '';
            editType.value = 'oai';
            editApiBase.value = '';
            editModel.value = '';
            editApiKey.value = '';
            keyEditorError.value = '';
            keyEditorNotice.value = '';
            keyEditorOpen.value = true;
            nextTick(() => {
                if (window.lucide) lucide.createIcons();
            });
        };

        const closeKeyEditor = () => {
            keyEditorOpen.value = false;
            editingConfigId.value = '';
            editApiKey.value = '';
            keyEditorError.value = '';
            keyEditorNotice.value = '';
            keyEditorTestOk.value = false;
            keyEditorTestFingerprint.value = '';
        };

        const testKeyEditor = async () => {
            try {
                if (keyEditorBusy.value) return false;
                keyEditorTesting.value = true;
                keyEditorError.value = '';
                keyEditorNotice.value = '';
                const payload = {
                    type: editType.value,
                    apibase: editApiBase.value || '',
                    model: editModel.value || '',
                    apikey: editApiKey.value || ''
                };
                if (editingConfigId.value) payload.id = editingConfigId.value;
                const res = await fetch('/api/llm_configs/test', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const out = await res.json().catch(() => ({}));
                if (!res.ok || !out || out.ok !== true) {
                    keyEditorError.value = (out && out.error) ? out.error : '测试失败';
                    keyEditorTestOk.value = false;
                    keyEditorTestFingerprint.value = '';
                    return false;
                }
                keyEditorNotice.value = out && out.url
                    ? `API 测试通过：${out.url}`
                    : 'API 测试通过';
                keyEditorTestOk.value = true;
                keyEditorTestFingerprint.value = makeKeyEditorFingerprint();
                return true;
            } catch (e) {
                keyEditorError.value = String(e && e.message ? e.message : e);
                keyEditorTestOk.value = false;
                keyEditorTestFingerprint.value = '';
                return false;
            } finally {
                keyEditorTesting.value = false;
            }
        };

        const saveKeyEditor = async () => {
            try {
                if (keyEditorBusy.value) return;
                if (!keyEditorTestOk.value || keyEditorTestFingerprint.value !== makeKeyEditorFingerprint()) {
                    keyEditorError.value = '请先通过 API 测试';
                    return;
                }
                keyEditorSaving.value = true;
                keyEditorError.value = '';
                keyEditorNotice.value = '';
                if (!editingConfigId.value && !String(editApiKey.value || '').trim()) {
                    keyEditorError.value = '新增模型必须填写 Key，保存后才会出现在列表里';
                    return;
                }
                const payload = {
                    type: editType.value,
                    apibase: editApiBase.value || '',
                    model: editModel.value || '',
                    apikey: editApiKey.value || ''
                };
                if (editingConfigId.value) payload.id = editingConfigId.value;

                const res = await fetch('/api/llm_configs/upsert', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                if (!res.ok) {
                    const err = await res.json().catch(() => ({}));
                    keyEditorError.value = err.error || '保存失败';
                    return;
                }
                const reloadRes = await reloadAgent();
                if (!reloadRes || !reloadRes.ok) {
                    keyEditorError.value = (reloadRes && reloadRes.error) ? reloadRes.error : '重载失败';
                    return;
                }
                await fetchStatus();
                await fetchLlmConfigs();
                const llmList = Array.isArray(status.value && status.value.llm_list) ? status.value.llm_list : [];
                if (!llmList.length) {
                    keyEditorError.value = '保存成功，但重载后没有加载出模型列表，请检查后端日志和模型配置';
                    return;
                }
                keyEditorNotice.value = '已保存并完成重载';
                closeKeyEditor();
            } catch (e) {
                console.error('Save llm config failed:', e);
            } finally {
                keyEditorSaving.value = false;
            }
        };

        const deleteConfig = async () => {
            if (!editingConfigId.value) return;
            try {
                const res = await fetch('/api/llm_configs/delete', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ id: editingConfigId.value })
                });
                if (!res.ok) return;
                await fetchLlmConfigs();
                await reloadAgent();
                await fetchStatus();
                const llmList = Array.isArray(status.value && status.value.llm_list) ? status.value.llm_list : [];
                if (!llmList.length) {
                    keyEditorError.value = '删除后模型列表为空，已保留编辑器便于继续配置';
                    return;
                }
                closeKeyEditor();
            } catch (e) {
                console.error('Delete llm config failed:', e);
            }
        };

        const fetchToDo = async () => {
            if (!currentUser.value) return;
            try {
                const res = await fetch('/api/todo');
                if (!res.ok) return;
                const data = await res.json();
                todoContent.value = data.content || '';
            } catch (e) {
                console.error('Fetch todo failed:', e);
            }
        };

        const saveToDo = async () => {
            try {
                await fetch('/api/todo', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ content: todoContent.value || '' })
                });
                closeModal();
            } catch (e) {
                console.error('Save todo failed:', e);
            }
        };

        const fetchSopList = async () => {
            if (!currentUser.value) return false;
            try {
                const res = await fetch('/api/sop/list');
                if (!res.ok) return false;
                const data = await res.json();
                sopFiles.value = data.files || [];
                if (!selectedSop.value && sopFiles.value.length) {
                    await selectSop(sopFiles.value[0]);
                }
                return true;
            } catch (e) {
                console.error('Fetch sop list failed:', e);
                return false;
            }
        };

        const sopEditMode = ref(false);
        const sopDraft = ref('');

        const selectSop = async (name) => {
            selectedSop.value = name;
            sopContent.value = '';
            sopEditMode.value = false;
            sopDraft.value = '';
            try {
                const res = await fetch(`/api/sop/read?name=${encodeURIComponent(name)}`);
                if (!res.ok) return;
                const data = await res.json();
                sopContent.value = data.content || '';
                sopDraft.value = sopContent.value;
            } catch (e) {
                console.error('Read sop failed:', e);
            }
        };

        const reloadSop = async () => {
            if (!selectedSop.value) return;
            await selectSop(selectedSop.value);
        };

        const startEditSop = async () => {
            if (!selectedSop.value) return;
            if (!sopDraft.value) sopDraft.value = sopContent.value || '';
            sopEditMode.value = true;
        };

        const cancelEditSop = async () => {
            sopDraft.value = sopContent.value || '';
            sopEditMode.value = false;
        };

        const saveSop = async () => {
            if (!selectedSop.value) return;
            try {
                const res = await fetch('/api/sop/write', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name: selectedSop.value, content: sopDraft.value || '' })
                });
                if (!res.ok) return;
                sopContent.value = sopDraft.value || '';
                sopEditMode.value = false;
                await fetchSopList();
            } catch (e) {
                console.error('Save sop failed:', e);
            }
        };

        const refreshScheduleList = async () => {
            if (!currentUser.value) return;
            try {
                const res = await fetch('/api/schedule/list');
                if (!res.ok) return;
                const data = await res.json();
                scheduleFiles.value = {
                    pending: data.pending || [],
                    running: data.running || [],
                    done: data.done || []
                };
            } catch (e) {
                console.error('Fetch schedule list failed:', e);
            }
        };

        const selectSchedule = async (bucket, name) => {
            selectedScheduleBucket.value = bucket;
            selectedScheduleName.value = name;
            scheduleContent.value = '';
            try {
                const res = await fetch(`/api/schedule/read?bucket=${encodeURIComponent(bucket)}&name=${encodeURIComponent(name)}`);
                if (!res.ok) return;
                const data = await res.json();
                scheduleContent.value = data.content || '';
            } catch (e) {
                console.error('Read schedule failed:', e);
            }
        };

        const saveSchedule = async () => {
            if (!selectedScheduleBucket.value || !selectedScheduleName.value) return;
            try {
                await fetch('/api/schedule/write', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        bucket: selectedScheduleBucket.value,
                        name: selectedScheduleName.value,
                        content: scheduleContent.value || ''
                    })
                });
                await refreshScheduleList();
            } catch (e) {
                console.error('Save schedule failed:', e);
            }
        };

        const deleteSchedule = async () => {
            if (!selectedScheduleBucket.value || !selectedScheduleName.value) return;
            try {
                await fetch('/api/schedule/delete', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        bucket: selectedScheduleBucket.value,
                        name: selectedScheduleName.value
                    })
                });
                selectedScheduleBucket.value = '';
                selectedScheduleName.value = '';
                scheduleContent.value = '';
                await refreshScheduleList();
            } catch (e) {
                console.error('Delete schedule failed:', e);
            }
        };

        const newScheduleTask = () => {
            const d = new Date();
            const pad = (n) => String(n).padStart(2, '0');
            const name = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}_${pad(d.getHours())}${pad(d.getMinutes())}_task.md`;
            selectedScheduleBucket.value = 'pending';
            selectedScheduleName.value = name;
            scheduleContent.value = '';
        };

        const toggleScheduler = async () => {
            try {
                await fetch('/api/control', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ action: 'toggle_scheduler' })
                });
                await fetchStatus();
            } catch (e) {
                console.error('Toggle scheduler failed:', e);
            }
        };

        const setSchedulerInterval = async () => {
            try {
                await fetch('/api/control', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ action: 'set_scheduler_interval', value: status.value.scheduler_interval })
                });
                await fetchStatus();
            } catch (e) {
                console.error('Set scheduler interval failed:', e);
            }
        };

        const stopTask = async () => {
            try {
                pushStreamDebug('stop-start', {
                    run_states: runStates.size,
                    active_runs: activeStreamRuns,
                });
                if (currentSubmitAbortController) {
                    try { currentSubmitAbortController.abort(); } catch {}
                    currentSubmitAbortController = null;
                }
                const pendingRunIds = Array.from(pendingSubmissions.values())
                    .map((x) => x && x.run_id ? String(x.run_id) : '')
                    .filter(Boolean);
                const activeRunIds = Array.from(runStates.keys());
                const runIds = Array.from(new Set([...pendingRunIds, ...activeRunIds]));
                pendingSubmissions.clear();
                submitInFlight.value = false;
                for (const rid of runIds) {
                    const st = runStates.get(rid);
                    if (!st) continue;
                    if (st.flushTimer) {
                        clearTimeout(st.flushTimer);
                        st.flushTimer = null;
                    }
                    const msg = messages.value[st.assistantIndex];
                    if (msg) {
                        const buf = st.buffer || '';
                        st.buffer = '';
                        if (buf) {
                            if (Array.isArray(msg.parts)) msg.parts.push(buf);
                            msg.totalLen = (msg.totalLen || 0) + buf.length;
                        }
                        if (msg.content === '' && Array.isArray(msg.parts) && msg.parts.length) {
                            msg.content = msg.parts.join('');
                        }
                        msg.streaming = false;
                        finalizeMessage(msg);
                    }
                    runStates.delete(rid);
                }
                isTyping.value = false;
                submissionNotice.value = runIds.length > 0 ? '已请求停止当前任务' : '已放弃当前等待';
                
                await fetch('/api/control', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ action: 'stop', run_ids: runIds })
                });
                pushStreamDebug('stop-requested', { run_ids: runIds.length });
                fetchStatus();
            } catch (e) {
                console.error('Stop task failed:', e);
            }
        };

        const clearHistory = async () => {
             try {
                await fetch('/api/control', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ action: 'clear_history' })
                });
                messages.value = [];
                renderLimit.value = 120;
                stickToBottom.value = true;
             } catch (e) {
                 console.error('Clear history failed:', e);
             }
        };

        const toggleAutonomous = async () => {
            try {
                await fetch('/api/control', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ action: 'toggle_autonomous' })
                });
                fetchStatus();
            } catch (e) {
                console.error('Toggle autonomous failed:', e);
            }
        };

        const triggerAutonomous = async () => {
             try {
                await fetch('/api/control', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ action: 'trigger_autonomous' })
                });
                fetchStatus();
            } catch (e) {
                console.error('Trigger autonomous failed:', e);
            }
        };

        const injectSysPrompt = async () => {
             try {
                await fetch('/api/control', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ action: 'inject_sys_prompt' })
                });
            } catch (e) {
                console.error('Inject sys prompt failed:', e);
            }
        };

        const updateThreshold = async () => {
             try {
                await fetch('/api/control', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ action: 'set_autonomous_threshold', value: status.value.autonomous_threshold })
                });
                // We don't fetchStatus immediately to avoid UI glitch if server is slow
            } catch (e) {
                console.error('Update threshold failed:', e);
            }
        };

        const formatTime = (seconds) => {
            if (!seconds) return '0s';
            const m = Math.floor(seconds / 60);
            const s = Math.floor(seconds % 60);
            return `${m}m ${s}s`;
        };

        const fetchAdminUsers = async () => {
            if (!isAdmin.value) return false;
            try {
                adminBusy.value = true;
                adminError.value = '';
                adminNotice.value = '';
                const params = new URLSearchParams({
                    q: adminUserSearch.value || '',
                    role: adminRoleFilter.value || 'all',
                    status: adminStatusFilter.value || 'all',
                    page: '1',
                    page_size: '200',
                });
                const res = await fetch(`/api/admin/users?${params.toString()}`);
                const data = await res.json().catch(() => ({}));
                if (!res.ok) {
                    adminError.value = data.error || '加载用户列表失败';
                    return false;
                }
                adminUsers.value = data.users || [];
                if (!selectedAdminUsername.value && adminUsers.value.length) {
                    selectedAdminUsername.value = adminUsers.value[0].username;
                    copyTargetUsername.value = adminUsers.value[0].username;
                } else if (selectedAdminUsername.value && !adminUsers.value.some((user) => user.username === selectedAdminUsername.value)) {
                    selectedAdminUsername.value = adminUsers.value.length ? adminUsers.value[0].username : '';
                }
                syncSelectedAdminLimits();
                const validTargets = new Set(adminUsers.value.map((user) => user.username));
                adminSelectedTargets.value = adminSelectedTargets.value.filter((username) => validTargets.has(username));
                if (!copyTargetUsername.value || !validTargets.has(copyTargetUsername.value)) {
                    copyTargetUsername.value = adminUsers.value.length ? adminUsers.value[0].username : '';
                }
                return true;
            } catch (e) {
                adminError.value = String(e && e.message ? e.message : e);
                return false;
            } finally {
                adminBusy.value = false;
            }
        };

        const fetchAdminFiles = async () => {
            if (!isAdmin.value || !selectedAdminUsername.value) return false;
            try {
                adminBusy.value = true;
                adminError.value = '';
                adminNotice.value = '';
                adminFileContent.value = '';
                selectedAdminFilePath.value = '';
                const res = await fetch(`/api/admin/files/tree?username=${encodeURIComponent(selectedAdminUsername.value)}&scope=${encodeURIComponent(adminScope.value)}`);
                const data = await res.json().catch(() => ({}));
                if (!res.ok) {
                    adminError.value = data.error || '加载文件列表失败';
                    adminFiles.value = [];
                    return false;
                }
                adminFiles.value = data.items || [];
                return true;
            } catch (e) {
                adminError.value = String(e && e.message ? e.message : e);
                adminFiles.value = [];
                return false;
            } finally {
                adminBusy.value = false;
            }
        };

        const selectAdminFile = async (path) => {
            if (!path || !selectedAdminUsername.value) return;
            try {
                adminBusy.value = true;
                adminError.value = '';
                adminNotice.value = '';
                selectedAdminFilePath.value = path;
                copyTargetPath.value = path;
                batchCopyPath.value = path;
                adminUploadPath.value = path;
                adminRenamePath.value = path;
                adminFileEditMode.value = false;
                const res = await fetch(`/api/admin/files/read?username=${encodeURIComponent(selectedAdminUsername.value)}&scope=${encodeURIComponent(adminScope.value)}&path=${encodeURIComponent(path)}`);
                const data = await res.json().catch(() => ({}));
                if (!res.ok) {
                    adminError.value = data.error || '读取文件失败';
                    adminFileContent.value = '';
                    adminFileDraft.value = '';
                    return;
                }
                adminFileContent.value = data.content || '';
                adminFileDraft.value = data.content || '';
            } catch (e) {
                adminError.value = String(e && e.message ? e.message : e);
                adminFileContent.value = '';
                adminFileDraft.value = '';
            } finally {
                adminBusy.value = false;
            }
        };

        const copyAdminFile = async () => {
            if (!selectedAdminUsername.value || !selectedAdminFilePath.value || !copyTargetUsername.value) {
                adminError.value = '请先选择源用户、源文件和目标用户';
                return;
            }
            try {
                adminBusy.value = true;
                adminError.value = '';
                adminNotice.value = '';
                const res = await fetch('/api/admin/files/copy', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        source_username: selectedAdminUsername.value,
                        target_username: copyTargetUsername.value,
                        scope: adminScope.value,
                        path: selectedAdminFilePath.value,
                        target_path: copyTargetPath.value || selectedAdminFilePath.value,
                    }),
                });
                const data = await res.json().catch(() => ({}));
                if (!res.ok) {
                    adminError.value = data.error || '复制失败';
                    return;
                }
                adminNotice.value = `已复制到 ${copyTargetUsername.value}`;
                if (copyTargetUsername.value === selectedAdminUsername.value) {
                    await fetchAdminFiles();
                }
                await fetchAuditLogs();
            } catch (e) {
                adminError.value = String(e && e.message ? e.message : e);
            } finally {
                adminBusy.value = false;
            }
        };

        const createAdminUser = async () => {
            if (!createUsername.value || !createPassword.value) {
                adminError.value = '请输入用户名和密码';
                return;
            }
            try {
                adminBusy.value = true;
                adminError.value = '';
                adminNotice.value = '';
                const res = await fetch('/api/admin/users', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        username: createUsername.value,
                        password: createPassword.value,
                        is_admin: createIsAdmin.value,
                    }),
                });
                const data = await res.json().catch(() => ({}));
                if (!res.ok) {
                    adminError.value = data.error || '创建用户失败';
                    return;
                }
                createUsername.value = '';
                createPassword.value = '';
                createIsAdmin.value = false;
                adminNotice.value = '用户已创建';
                await fetchAdminUsers();
                await fetchAuditLogs();
            } catch (e) {
                adminError.value = String(e && e.message ? e.message : e);
            } finally {
                adminBusy.value = false;
            }
        };

        const adminResetUserPassword = async () => {
            if (!selectedAdminUsername.value || !adminResetPassword.value) {
                adminError.value = '请选择用户并输入新密码';
                return;
            }
            try {
                adminBusy.value = true;
                adminError.value = '';
                adminNotice.value = '';
                const res = await fetch('/api/admin/users/password', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        username: selectedAdminUsername.value,
                        new_password: adminResetPassword.value,
                    }),
                });
                const data = await res.json().catch(() => ({}));
                if (!res.ok) {
                    adminError.value = data.error || '重置密码失败';
                    return;
                }
                adminResetPassword.value = '';
                adminNotice.value = `已重置 ${selectedAdminUsername.value} 的密码`;
                await fetchAdminUsers();
                await fetchAuditLogs();
            } catch (e) {
                adminError.value = String(e && e.message ? e.message : e);
            } finally {
                adminBusy.value = false;
            }
        };

        const adminToggleUserStatus = async (nextActive) => {
            if (!selectedAdminUsername.value) {
                adminError.value = '请先选择用户';
                return;
            }
            try {
                adminBusy.value = true;
                adminError.value = '';
                adminNotice.value = '';
                const res = await fetch('/api/admin/users/status', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        username: selectedAdminUsername.value,
                        is_active: !!nextActive,
                    }),
                });
                const data = await res.json().catch(() => ({}));
                if (!res.ok) {
                    adminError.value = data.error || '更新账号状态失败';
                    return;
                }
                adminNotice.value = nextActive ? `已启用 ${selectedAdminUsername.value}` : `已禁用 ${selectedAdminUsername.value}`;
                await fetchAdminUsers();
                if (!nextActive && selectedAdminUsername.value === currentUser.value.username) {
                    await logout();
                    return;
                }
                if (selectedAdminUsername.value) {
                    await fetchAdminFiles();
                }
                await fetchAuditLogs();
            } catch (e) {
                adminError.value = String(e && e.message ? e.message : e);
            } finally {
                adminBusy.value = false;
            }
        };

        const toggleAdminTarget = (username) => {
            if (!username || username === selectedAdminUsername.value) return;
            if (adminSelectedTargets.value.includes(username)) {
                adminSelectedTargets.value = adminSelectedTargets.value.filter((item) => item !== username);
            } else {
                adminSelectedTargets.value = [...adminSelectedTargets.value, username];
            }
        };

        const chooseAdminUser = async (username) => {
            selectedAdminUsername.value = username || '';
            copyTargetUsername.value = username || '';
            syncSelectedAdminLimits();
            await fetchAdminFiles();
        };

        const toggleAllFilteredTargets = () => {
            const candidates = filteredAdminUsers.value
                .map((user) => user.username)
                .filter((username) => username !== selectedAdminUsername.value);
            if (!candidates.length) return;
            if (allFilteredTargetsSelected.value) {
                adminSelectedTargets.value = adminSelectedTargets.value.filter((username) => !candidates.includes(username));
                return;
            }
            const merged = new Set(adminSelectedTargets.value);
            candidates.forEach((username) => merged.add(username));
            adminSelectedTargets.value = Array.from(merged);
        };

        const batchCopyAdminFile = async () => {
            if (!selectedAdminUsername.value || !selectedAdminFilePath.value) {
                adminError.value = '请先选择源用户和源文件';
                return;
            }
            if (!adminSelectedTargets.value.length) {
                adminError.value = '请先选择至少一个批量分发目标用户';
                return;
            }
            try {
                adminBusy.value = true;
                adminError.value = '';
                adminNotice.value = '';
                const res = await fetch('/api/admin/files/copy_batch', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        source_username: selectedAdminUsername.value,
                        target_usernames: adminSelectedTargets.value,
                        scope: adminScope.value,
                        path: selectedAdminFilePath.value,
                        target_path: batchCopyPath.value || selectedAdminFilePath.value,
                    }),
                });
                const data = await res.json().catch(() => ({}));
                if (!res.ok) {
                    adminError.value = data.error || '批量复制失败';
                    return;
                }
                const copiedCount = Array.isArray(data.copied) ? data.copied.length : 0;
                const skippedCount = Array.isArray(data.skipped) ? data.skipped.length : 0;
                adminNotice.value = skippedCount > 0
                    ? `已分发 ${copiedCount} 个用户，跳过 ${skippedCount} 个`
                    : `已分发到 ${copiedCount} 个用户`;
                await fetchAuditLogs();
            } catch (e) {
                adminError.value = String(e && e.message ? e.message : e);
            } finally {
                adminBusy.value = false;
            }
        };

        const uploadAdminFile = async (event) => {
            const input = event && event.target;
            const file = input && input.files && input.files[0];
            if (!file) return;
            if (!selectedAdminUsername.value) {
                adminError.value = '请先选择源用户';
                if (input) input.value = '';
                return;
            }
            try {
                adminBusy.value = true;
                adminError.value = '';
                adminNotice.value = '';
                const form = new FormData();
                form.append('source_username', selectedAdminUsername.value);
                form.append('scope', adminScope.value);
                form.append('target_path', adminUploadPath.value || file.name);
                form.append('file', file);
                const res = await fetch('/api/admin/files/upload', {
                    method: 'POST',
                    body: form,
                });
                const data = await res.json().catch(() => ({}));
                if (!res.ok) {
                    adminError.value = data.error || '上传失败';
                    return;
                }
                adminUploadFileName.value = file.name;
                adminUploadPath.value = data.path || adminUploadPath.value || file.name;
                adminNotice.value = `已上传 ${file.name}`;
                await fetchAdminFiles();
                if (data.path) {
                    await selectAdminFile(data.path);
                }
                await fetchAuditLogs();
            } catch (e) {
                adminError.value = String(e && e.message ? e.message : e);
            } finally {
                adminBusy.value = false;
                if (input) input.value = '';
            }
        };

        const startEditAdminFile = () => {
            if (!selectedAdminFilePath.value) return;
            adminFileDraft.value = adminFileContent.value || '';
            adminFileEditMode.value = true;
        };

        const cancelEditAdminFile = () => {
            adminFileDraft.value = adminFileContent.value || '';
            adminFileEditMode.value = false;
        };

        const saveAdminFile = async () => {
            if (!selectedAdminUsername.value || !selectedAdminFilePath.value) {
                adminError.value = '请先选择要保存的文件';
                return;
            }
            try {
                adminBusy.value = true;
                adminError.value = '';
                adminNotice.value = '';
                const res = await fetch('/api/admin/files/write', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        username: selectedAdminUsername.value,
                        scope: adminScope.value,
                        path: selectedAdminFilePath.value,
                        content: adminFileDraft.value || '',
                    }),
                });
                const data = await res.json().catch(() => ({}));
                if (!res.ok) {
                    adminError.value = data.error || '保存文件失败';
                    return;
                }
                adminFileContent.value = adminFileDraft.value || '';
                adminFileEditMode.value = false;
                adminNotice.value = '文件已保存';
                await fetchAuditLogs();
            } catch (e) {
                adminError.value = String(e && e.message ? e.message : e);
            } finally {
                adminBusy.value = false;
            }
        };

        const saveAdminLimits = async () => {
            if (!selectedAdminUsername.value) {
                adminError.value = '请先选择用户';
                return;
            }
            try {
                adminBusy.value = true;
                adminError.value = '';
                adminNotice.value = '';
                const res = await fetch('/api/admin/users/limits', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        username: selectedAdminUsername.value,
                        max_parallel_runs: Number(adminLimitParallel.value || 1),
                        max_prompt_chars: Number(adminLimitPrompt.value || 20000),
                        max_upload_bytes: Number(adminLimitUploadMb.value || 10) * 1024 * 1024,
                    }),
                });
                const data = await res.json().catch(() => ({}));
                if (!res.ok) {
                    adminError.value = data.error || '保存配额失败';
                    return;
                }
                adminNotice.value = '用户配额已更新';
                await fetchAdminUsers();
                await fetchAuditLogs();
            } catch (e) {
                adminError.value = String(e && e.message ? e.message : e);
            } finally {
                adminBusy.value = false;
            }
        };

        const createAdminPath = async () => {
            if (!selectedAdminUsername.value || !adminCreatePath.value) {
                adminError.value = '请先选择用户并填写要创建的路径';
                return;
            }
            try {
                adminBusy.value = true;
                adminError.value = '';
                adminNotice.value = '';
                const res = await fetch('/api/admin/files/create', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        username: selectedAdminUsername.value,
                        scope: adminScope.value,
                        path: adminCreatePath.value,
                        kind: adminCreateKind.value,
                    }),
                });
                const data = await res.json().catch(() => ({}));
                if (!res.ok) {
                    adminError.value = data.error || '创建失败';
                    return;
                }
                adminNotice.value = adminCreateKind.value === 'dir' ? '文件夹已创建' : '文件已创建';
                const createdPath = adminCreatePath.value;
                adminCreatePath.value = '';
                await fetchAdminFiles();
                if (adminCreateKind.value === 'file') {
                    await selectAdminFile(createdPath);
                }
                await fetchAuditLogs();
            } catch (e) {
                adminError.value = String(e && e.message ? e.message : e);
            } finally {
                adminBusy.value = false;
            }
        };

        const renameAdminPath = async () => {
            if (!selectedAdminUsername.value || !selectedAdminFilePath.value || !adminRenamePath.value) {
                adminError.value = '请先选择文件并填写新路径';
                return;
            }
            try {
                adminBusy.value = true;
                adminError.value = '';
                adminNotice.value = '';
                const oldPath = selectedAdminFilePath.value;
                const res = await fetch('/api/admin/files/rename', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        username: selectedAdminUsername.value,
                        scope: adminScope.value,
                        old_path: oldPath,
                        new_path: adminRenamePath.value,
                    }),
                });
                const data = await res.json().catch(() => ({}));
                if (!res.ok) {
                    adminError.value = data.error || '重命名失败';
                    return;
                }
                adminNotice.value = '路径已重命名';
                await fetchAdminFiles();
                await selectAdminFile(adminRenamePath.value);
                await fetchAuditLogs();
            } catch (e) {
                adminError.value = String(e && e.message ? e.message : e);
            } finally {
                adminBusy.value = false;
            }
        };

        const deleteAdminPath = async () => {
            if (!selectedAdminUsername.value || !selectedAdminFilePath.value) {
                adminError.value = '请先选择要删除的路径';
                return;
            }
            const targetPath = selectedAdminFilePath.value;
            if (!window.confirm(`确认删除 ${targetPath} 吗？`)) {
                return;
            }
            try {
                adminBusy.value = true;
                adminError.value = '';
                adminNotice.value = '';
                const res = await fetch('/api/admin/files/delete', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        username: selectedAdminUsername.value,
                        scope: adminScope.value,
                        path: targetPath,
                    }),
                });
                const data = await res.json().catch(() => ({}));
                if (!res.ok) {
                    adminError.value = data.error || '删除失败';
                    return;
                }
                adminNotice.value = '路径已删除';
                selectedAdminFilePath.value = '';
                adminFileContent.value = '';
                adminFileDraft.value = '';
                adminRenamePath.value = '';
                await fetchAdminFiles();
                await fetchAuditLogs();
            } catch (e) {
                adminError.value = String(e && e.message ? e.message : e);
            } finally {
                adminBusy.value = false;
            }
        };

        const fetchAuditLogs = async () => {
            if (!isAdmin.value) return false;
            try {
                const params = new URLSearchParams({
                    action: auditActionFilter.value || '',
                    target_username: auditTargetFilter.value || '',
                    limit: '80',
                });
                const res = await fetch(`/api/admin/audit_logs?${params.toString()}`);
                const data = await res.json().catch(() => ({}));
                if (!res.ok) {
                    adminError.value = data.error || '加载审计日志失败';
                    return false;
                }
                auditLogs.value = data.logs || [];
                return true;
            } catch (e) {
                adminError.value = String(e && e.message ? e.message : e);
                return false;
            }
        };

        const formatAuditTime = (ts) => {
            if (!ts) return '';
            try {
                return new Date(ts * 1000).toLocaleString();
            } catch (e) {
                return String(ts);
            }
        };

        const changePassword = async () => {
            if (!passwordOld.value || !passwordNew.value || !passwordConfirm.value) {
                passwordError.value = '请填写完整的密码信息';
                passwordNotice.value = '';
                return false;
            }
            if (passwordNew.value.length < 6) {
                passwordError.value = '新密码至少 6 位';
                passwordNotice.value = '';
                return false;
            }
            if (passwordNew.value !== passwordConfirm.value) {
                passwordError.value = '两次输入的新密码不一致';
                passwordNotice.value = '';
                return false;
            }
            try {
                passwordBusy.value = true;
                passwordError.value = '';
                passwordNotice.value = '';
                const res = await fetch('/api/auth/change_password', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        old_password: passwordOld.value,
                        new_password: passwordNew.value,
                        confirm_password: passwordConfirm.value,
                    }),
                });
                const data = await res.json().catch(() => ({}));
                if (!res.ok) {
                    passwordError.value = data.error || '修改密码失败';
                    return false;
                }
                passwordOld.value = '';
                passwordNew.value = '';
                passwordConfirm.value = '';
                passwordNotice.value = '密码已更新';
                return true;
            } catch (e) {
                passwordError.value = String(e && e.message ? e.message : e);
                passwordNotice.value = '';
                return false;
            } finally {
                passwordBusy.value = false;
            }
        };

        return {
            authReady,
            currentUser,
            isAdmin,
            selectedAdminUser,
            authMode,
            loginUsername,
            loginPassword,
            loginBusy,
            authError,
            authNotice,
            registerUsername,
            registerEmail,
            registerPassword,
            registerConfirmPassword,
            registerBusy,
            login,
            register,
            logout,
            sidebarOpen,
            inputMessage,
            messages,
            visibleMessages,
            hiddenCount,
            isTyping,
            submitInFlight,
            submissionNotice,
            status,
            activeModal,
            openModal,
            closeModal,
            toggleTheme,
            todoContent,
            saveToDo,
            sopFiles,
            selectedSop,
            sopContent,
            sopEditMode,
            sopDraft,
            selectSop,
            reloadSop,
            startEditSop,
            cancelEditSop,
            saveSop,
            scheduleFiles,
            selectedScheduleBucket,
            selectedScheduleName,
            scheduleContent,
            refreshScheduleList,
            selectSchedule,
            saveSchedule,
            deleteSchedule,
            newScheduleTask,
            toggleScheduler,
            setSchedulerInterval,
            adminUsers,
            selectedAdminUsername,
            adminScope,
            adminFiles,
            selectedAdminFilePath,
            adminFileContent,
            adminFileEditMode,
            adminFileDraft,
            adminBusy,
            adminError,
            adminNotice,
            adminUserSearch,
            adminRoleFilter,
            adminStatusFilter,
            filteredAdminUsers,
            adminSelectedTargets,
            allFilteredTargetsSelected,
            copyTargetUsername,
            copyTargetPath,
            batchCopyPath,
            adminUploadPath,
            adminUploadFileName,
            adminCreatePath,
            adminCreateKind,
            adminRenamePath,
            auditLogs,
            auditActionFilter,
            auditTargetFilter,
            adminLimitParallel,
            adminLimitPrompt,
            adminLimitUploadMb,
            createUsername,
            createPassword,
            createIsAdmin,
            adminResetPassword,
            passwordOld,
            passwordNew,
            passwordConfirm,
            passwordBusy,
            passwordError,
            passwordNotice,
            fetchAdminUsers,
            fetchAdminFiles,
            selectAdminFile,
            copyAdminFile,
            createAdminUser,
            adminResetUserPassword,
            adminToggleUserStatus,
            chooseAdminUser,
            toggleAdminTarget,
            toggleAllFilteredTargets,
            batchCopyAdminFile,
            uploadAdminFile,
            startEditAdminFile,
            cancelEditAdminFile,
            saveAdminFile,
            saveAdminLimits,
            createAdminPath,
            renameAdminPath,
            deleteAdminPath,
            fetchAuditLogs,
            formatAuditTime,
            changePassword,
            reloadAgent,
            sendMessage,
            renderMarkdown,
            copyToClipboard,
            switchLLM,
            stopTask,
            clearHistory,
            toggleAutonomous,
            triggerAutonomous,
             injectSysPrompt,
             formatTime,
             updateThreshold,
             onChatScroll,
             loadMoreHistory,
             jumpToLatest,
             stickToBottom,
             expandMessage,
             startNewModel,
             keyEditorOpen,
             editingConfigId,
             editType,
             editApiBase,
             editModel,
             editApiKey,
             editingTitle,
             editingHasKey,
             editingKeyLast4,
             openKeyEditor,
             closeKeyEditor,
             keyEditorBusy,
             keyEditorTestOk,
             testKeyEditor,
             saveKeyEditor,
             deleteConfig,
             keyEditorError,
             keyEditorNotice
         };
     }
}).mount('#app');
window.__A3_APP_READY__ = true;
document.documentElement.classList.add('js-ready');
