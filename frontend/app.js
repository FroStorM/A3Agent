const { createApp, ref, computed, onMounted, nextTick, watch } = Vue;

createApp({
    setup() {
        const sidebarOpen = ref(window.innerWidth > 768);
        const inputMessage = ref('');
        const selectedModeIds = ref([]);
        const pendingGoalMode = ref(null);
        const sessionMessages = ref({});
        const chatSessions = ref([]);
        const activeSessionId = ref('');
        const messages = computed(() => sessionMessages.value[activeSessionId.value] || []);
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
        const historySessions = ref([]);
        const selectedHistorySessionId = ref('');
        const selectedHistorySession = ref(null);
        const historyMessages = ref([]);
        const historyTitleDraft = ref('');
        const historyNotice = ref('');
        const historyLoading = ref(false);
        const historySavingTitle = ref(false);
        const historyError = ref('');
        const historySearchQuery = ref('');
        const historySearchResults = ref([]);
        const historySearchLoading = ref(false);
        const historySearchError = ref('');
        const historySearchActive = computed(() => !!String(historySearchQuery.value || '').trim());
        const memoryFiles = ref([]);
        const selectedMemoryFile = ref('');
        const memoryContent = ref('');
        const memoryRoot = ref('');
        const memoryLoading = ref(false);
        const memoryError = ref('');
        const backupRoot = ref('');
        const backupItems = ref([]);
        const backupLoading = ref(false);
        const backupCreating = ref(false);
        const backupNotice = ref('');
        const backupError = ref('');
        const petConfig = ref({
            enabled: true,
            size: 104,
            position: 'right-bottom',
            x: null,
            y: null,
            skin_name: 'legacy-pet',
            always_on_top: true,
            show_shadow: false,
            click_action: 'toggle_main'
        });
        const petConfigPath = ref('');
        const petSkins = ref([]);
        const petLoading = ref(false);
        const petSaving = ref(false);
        const petNotice = ref('');
        const petError = ref('');
        const llmConfigs = ref([]);
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
        const communicationTools = ref([]);
        const communicationPath = ref('');
        const selectedCommunicationId = ref('');
        const communicationDrafts = ref({});
        const communicationLoading = ref(false);
        const communicationSaving = ref(false);
        const communicationBusyId = ref('');
        const communicationNotice = ref('');
        const communicationError = ref('');
        const interventionOpen = ref(false);
        const interventionText = ref('');
        const interventionNotice = ref('');
        const interventionError = ref('');
        const interventionSaving = ref(false);
        const attachedImages = ref([]);
        const attachmentError = ref('');
        const attachmentUploading = ref(false);
        const fileInputRef = ref(null);
        const isComposing = ref(false);
        const goalState = ref(null);
        const goalObjective = ref('');
        const goalBudgetMinutes = ref(30);
        const goalMaxTurns = ref(80);
        const goalDonePrompt = ref('');
        const goalLoading = ref(false);
        const goalNotice = ref('');
        const goalError = ref('');
        const hiveState = ref(null);
        const hiveObjective = ref('');
        const hiveBudgetMinutes = ref(30);
        const hiveMaxTurns = ref(80);
        const hiveWorkerCount = ref(2);
        const hiveLoading = ref(false);
        const hiveNotice = ref('');
        const hiveError = ref('');
        const orchestrationTab = ref('goal');
        const hivePosts = ref([]);
        const hivePostsLoading = ref(false);
        const hivePostsError = ref('');
        const hiveBbsOffline = ref(false);
        const hiveBbsUrl = ref('');
        const hivePostAuthor = ref('human');
        const hivePostContent = ref('');
        const hivePosting = ref(false);
        const hiveAutoRefresh = ref(true);
        const hivePostFilter = ref('all');
        const hivePostSearch = ref('');
        const hiveControlTarget = ref('all');
        const hiveExtendMinutes = ref(10);
        const hiveExtendTurns = ref(20);
        const hiveBbsComposerOpen = ref(false);
        const hiveExpandedPosts = ref({});
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
        const hiveFilteredPosts = computed(() => {
            const role = hivePostFilter.value || 'all';
            const q = String(hivePostSearch.value || '').trim().toLowerCase();
            return (hivePosts.value || []).filter((post) => {
                const author = String(post.author || '').toLowerCase();
                const content = String(post.content || '').toLowerCase();
                const roleOk =
                    role === 'all' ||
                    (role === 'master' && author.includes('master')) ||
                    (role === 'worker' && author.includes('worker')) ||
                    (role === 'human' && (author.includes('human') || author.includes('user'))) ||
                    (role === 'system' && (author.includes('seed') || author.includes('system')));
                const qOk = !q || author.includes(q) || content.includes(q);
                return roleOk && qOk;
            });
        });

        const workspacePath = ref("");
        const workspaceOptions = ref([]);
        const workspaceSelected = ref("");
        const apiReady = ref(false);
        let bootstrapLoaded = false;

        const modeCommands = [
            {
                id: 'plan',
                label: '@plan',
                title: 'Plan 模式',
                desc: '先拆解步骤、再执行与验证',
                prompt: '@plan 请进入计划模式：先把目标拆成可执行步骤，确认风险和验证方式，再按步骤推进。'
            },
            {
                id: 'watcher',
                label: '@watch',
                title: '监察者模式',
                desc: '让 GA 主动巡检待办和状态',
                prompt: '@watch 请以监察者模式运行：检查当前 workspace、ToDo、计划任务和潜在问题，必要时提醒我确认。'
            },
            {
                id: 'sop',
                label: '@sop',
                title: 'SOP 模式',
                desc: '按 SOP 技能库约束执行',
                prompt: '@sop 请先匹配最相关的 SOP，再严格按 SOP 步骤执行并说明使用了哪个 SOP。'
            },
            {
                id: 'review',
                label: '@review',
                title: 'Review 模式',
                desc: '优先找问题、风险和缺测试',
                prompt: '@review 请进入审查模式：优先列出缺陷、风险、回归点和缺失验证，不要先做泛泛总结。'
            },
            {
                id: 'goal',
                label: '@goal',
                title: 'Goal 模式',
                desc: '围绕明确目标持续推进',
                prompt: '@goal 请进入目标模式：先明确最终目标、成功标准和当前约束，再持续围绕目标推进；必要时主动拆解子目标、更新进展并提醒我关键决策。'
            }
        ];
        const selectedModeCommands = computed(() => modeCommands.filter((mode) => selectedModeIds.value.includes(mode.id)));

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
        const runningSessionIds = ref(new Set());
        const activeSessionRunning = computed(() => !!(activeSessionId.value && runningSessionIds.value.has(activeSessionId.value)));
        const updateRunningSession = (sessionId, running) => {
            if (!sessionId) return;
            const next = new Set(runningSessionIds.value);
            if (running) next.add(sessionId);
            else next.delete(sessionId);
            runningSessionIds.value = next;
            chatSessions.value = chatSessions.value.map((s) => (
                s.session_id === sessionId ? { ...s, status: running ? 'running' : (s.status === 'running' ? 'idle' : s.status) } : s
            ));
        };
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

        const syncWorkspaceSelection = (current, options) => {
            const opts = Array.isArray(options) ? options.filter((x) => typeof x === 'string' && x) : [];
            if (current && !opts.includes(current)) {
                opts.unshift(current);
            }
            workspaceOptions.value = opts;
            if (current) {
                workspacePath.value = current;
            }
            if (current && opts.includes(current)) {
                workspaceSelected.value = current;
            } else if (!workspaceSelected.value && opts.length) {
                workspaceSelected.value = opts[0];
            }
        };

        // Workspace setup
        const fetchWorkspace = async () => {
            try {
                const res = await fetch('/api/workspace/get');
                if (!res.ok) return false;
                const data = await res.json();
                if (data && data.workspace) {
                    workspacePath.value = data.workspace;
                    if (!workspaceSelected.value) workspaceSelected.value = data.workspace;
                }
                return true;
            } catch (e) {
                console.error("Failed to fetch workspace", e);
                return false;
            }
        };

        const fetchWorkspaceOptions = async () => {
            try {
                const res = await fetch('/api/workspace/options');
                if (!res.ok) return false;
                const data = await res.json();
                const cur = typeof data.current === 'string' && data.current ? data.current : workspacePath.value;
                syncWorkspaceSelection(cur, data.options);
                return true;
            } catch (e) {
                console.error("Failed to fetch workspace options", e);
                return false;
            }
        };

        const setWorkspace = async () => {
            const target = workspaceSelected.value || workspacePath.value;
            if (!target) return;
            try {
                const res = await fetch('/api/workspace/set', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ path: target })
                });
                const data = await res.json();
                if (data.status === 'ok') {
                    workspacePath.value = data.workspace || target;
                    workspaceSelected.value = data.workspace || target;
                    await fetchLlmConfigs();
                    await fetchSopList();
                    await fetchWorkspaceOptions();
                    closeModal();
                } else {
                    alert('Failed to update workspace: ' + data.error);
                }
            } catch (e) {
                alert("Failed to update workspace");
                console.error(e);
            }
        };

        // Load Lucide icons
        onMounted(() => {
            if (window.lucide) lucide.createIcons();

            // Theme toggle button
            const btn = document.getElementById('themeToggle');
            if (btn) btn.addEventListener('click', toggleTheme);

            ensureBackendDataLoaded();
            // Poll status every 5 seconds
            setInterval(async () => {
                const ok = await fetchStatus();
                if (ok && !bootstrapLoaded) {
                    await ensureBackendDataLoaded();
                }
            }, 5000);
            setInterval(async () => {
                if (activeModal.value === 'orchestration' && orchestrationTab.value === 'hive' && hiveAutoRefresh.value) {
                    await fetchHiveStatus();
                    await fetchHivePosts();
                } else if (!activeModal.value) {
                    await fetchHiveStatus();
                }
            }, 5000);

            if (!sseWatchdogTimer) {
                sseWatchdogTimer = setInterval(() => {
                    const idleMs = Date.now() - lastStreamSeenAt;
                    if (idleMs > 45000 || !eventSource || eventSource.readyState === EventSource.CLOSED) {
                        reconnectStream(`watchdog-${Math.round(idleMs / 1000)}s`);
                    }
                }, 15000);
            }

            window.addEventListener('focus', () => {
                recoverAfterIdle('window-focus');
            });
            document.addEventListener('visibilitychange', () => {
                if (!document.hidden) recoverAfterIdle('visibility');
            });
	            
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
                if (window.innerWidth <= 768) {
                    sidebarOpen.value = false;
                }
            });
            
            // Connect to Global Stream
            initStream();
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
        let sseWatchdogTimer = null;
        let lastStreamSeenAt = Date.now();
        const runStates = new Map();
        let activeStreamRuns = 0;
        const activeRunCount = ref(0);
        const runStateCount = ref(0);
        const streamViewMax = 60000;
        const streamTailMax = 16000;
        let scrollScheduled = false;

        const syncStreamActivityState = () => {
            activeRunCount.value = activeStreamRuns;
            runStateCount.value = runStates.size;
        };

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

        const setSessionMessages = (sessionId, items) => {
            if (!sessionId) return;
            sessionMessages.value = {
                ...sessionMessages.value,
                [sessionId]: Array.isArray(items) ? items : []
            };
        };

        const pushSessionMessage = (sessionId, msg) => {
            const sid = sessionId || activeSessionId.value;
            if (!sid || !msg) return -1;
            const list = [...(sessionMessages.value[sid] || []), msg];
            setSessionMessages(sid, list);
            return list.length - 1;
        };

        const updateSessionMessage = (sessionId, index, updater) => {
            const sid = sessionId || activeSessionId.value;
            const list = [...(sessionMessages.value[sid] || [])];
            if (index < 0 || index >= list.length) return null;
            const msg = list[index];
            if (typeof updater === 'function') updater(msg);
            list[index] = msg;
            setSessionMessages(sid, list);
            return msg;
        };

        const hasLiveRunForSession = (sessionId) => {
            if (!sessionId) return false;
            for (const st of runStates.values()) {
                if (st && st.sessionId === sessionId) return true;
            }
            return false;
        };

        const normalizeSessionPayloadMessages = (items) => {
            return (Array.isArray(items) ? items : [])
                .filter((item) => item && (item.role === 'user' || item.role === 'assistant'))
                .map((item) => makeMessage(item.role, item.content || '', {
                    timestamp: item.timestamp || item.created_at || '',
                    source: item.source,
                    run_id: item.run_id
                }));
        };

        const fetchSessions = async () => {
            try {
                const res = await fetch('/api/sessions');
                if (!res.ok) return false;
                const data = await res.json();
                chatSessions.value = Array.isArray(data.sessions) ? data.sessions : [];
                runningSessionIds.value = new Set(chatSessions.value.filter((s) => s.status === 'running').map((s) => s.session_id));
                const nextId = data.active_session_id || activeSessionId.value || ((chatSessions.value[0] || {}).session_id || '');
                if (nextId && nextId !== activeSessionId.value) {
                    await switchChatSession(nextId, false);
                } else if (nextId && !sessionMessages.value[nextId]) {
                    await loadChatSession(nextId);
                }
                return true;
            } catch (e) {
                console.error('Fetch sessions failed:', e);
                return false;
            }
        };

        const loadChatSession = async (sessionId) => {
            if (!sessionId) return false;
            try {
                const res = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}`);
                if (!res.ok) return false;
                const data = await res.json();
                setSessionMessages(sessionId, normalizeSessionPayloadMessages(data.messages));
                const idx = chatSessions.value.findIndex((s) => s.session_id === sessionId);
                const meta = {
                    session_id: data.session_id,
                    title: data.title,
                    summary: data.summary,
                    updated_at: data.updated_at,
                    message_count: data.message_count,
                    status: data.status || 'idle',
                    active: data.current
                };
                if (idx >= 0) {
                    const list = [...chatSessions.value];
                    list[idx] = { ...list[idx], ...meta };
                    chatSessions.value = list;
                }
                return true;
            } catch (e) {
                console.error('Load chat session failed:', e);
                return false;
            }
        };

        const switchChatSession = async (sessionId, activate = true) => {
            if (!sessionId) return;
            if (activate) {
                try {
                    await fetch(`/api/sessions/${encodeURIComponent(sessionId)}/activate`, { method: 'POST' });
                } catch (e) {
                    console.error('Activate session failed:', e);
                }
            }
            activeSessionId.value = sessionId;
            chatSessions.value = chatSessions.value.map((s) => ({ ...s, active: s.session_id === sessionId }));
            isTyping.value = activeSessionRunning.value;
            if (!hasLiveRunForSession(sessionId) || !(sessionMessages.value[sessionId] || []).length) {
                await loadChatSession(sessionId);
            }
            renderLimit.value = Math.min(renderMax, Math.max(120, (sessionMessages.value[sessionId] || []).length || 120));
            await nextTick();
            scrollToBottom();
        };

        const createChatSession = async () => {
            try {
                const res = await fetch('/api/sessions', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({})
                });
                const data = await res.json().catch(() => ({}));
                if (!res.ok || data.error) throw new Error(data.error || `HTTP ${res.status}`);
                await fetchSessions();
                const sid = data.active_session_id || (data.session && data.session.session_id);
                if (sid) await switchChatSession(sid, false);
            } catch (e) {
                console.error('Create session failed:', e);
            }
        };

        const closeChatSession = async (sessionId, event) => {
            if (event && typeof event.stopPropagation === 'function') event.stopPropagation();
            if (!sessionId) return;
            const before = [...chatSessions.value];
            const closingIndex = before.findIndex((s) => s.session_id === sessionId);
            const wasActive = sessionId === activeSessionId.value;
            const fallbackId = wasActive
                ? ((before[closingIndex + 1] || before[closingIndex - 1] || {}).session_id || '')
                : activeSessionId.value;
            try {
                const res = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}`, { method: 'DELETE' });
                const data = await res.json().catch(() => ({}));
                if (!res.ok || data.error) throw new Error(data.error || `HTTP ${res.status}`);
                const cache = { ...sessionMessages.value };
                delete cache[sessionId];
                sessionMessages.value = cache;
                const nextSessions = Array.isArray(data.sessions) ? data.sessions : before.filter((s) => s.session_id !== sessionId);
                chatSessions.value = nextSessions;
                runningSessionIds.value = new Set(nextSessions.filter((s) => s.status === 'running').map((s) => s.session_id));
                const nextId = data.active_session_id || fallbackId || ((nextSessions[0] || {}).session_id || '');
                if (nextId) {
                    await switchChatSession(nextId, false);
                } else {
                    await fetchSessions();
                }
            } catch (e) {
                console.error('Close session failed:', e);
            }
        };

        const fetchCurrentConversation = async () => {
            try {
                return await fetchSessions();
            } catch (e) {
                console.error('Fetch current conversation failed:', e);
                return false;
            }
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

        const reconnectStream = (reason = 'manual') => {
            pushStreamDebug('sse-reconnect', { reason });
            if (sseReconnectTimer) {
                clearTimeout(sseReconnectTimer);
                sseReconnectTimer = null;
            }
            if (eventSource) {
                try { eventSource.close(); } catch {}
                eventSource = null;
            }
            sseReconnectTimer = setTimeout(() => {
                sseReconnectTimer = null;
                initStream();
            }, reason === 'error' ? 3000 : 150);
        };

        const recoverAfterIdle = async (reason = 'focus') => {
            reconnectStream(reason);
            await fetchStatus();
            const running = !!(status.value && status.value.is_running) || activeStreamRuns > 0 || isTyping.value;
            if (!running) await fetchCurrentConversation();
            if (!bootstrapLoaded) await ensureBackendDataLoaded(3, 500);
        };
	        
        const initStream = () => {
            if (eventSource) eventSource.close();
            if (sseReconnectTimer) {
                clearTimeout(sseReconnectTimer);
                sseReconnectTimer = null;
            }
            lastStreamSeenAt = Date.now();

            if (window.location.protocol === 'file:' && !window.__BACKEND_PORT__) {
                fetch('/api/status')
                    .then(() => setTimeout(initStream, 50))
                    .catch((e) => {
                        pushStreamDebug('sse-port-wait', { error: String(e && e.message ? e.message : e) });
                        if (!sseReconnectTimer) reconnectStream('backend-port-wait');
                    });
                return;
            }
	            
            eventSource = new EventSource('/api/stream');
            pushStreamDebug('sse-open', { readyState: eventSource.readyState });
            eventSource.onopen = () => {
                lastStreamSeenAt = Date.now();
                pushStreamDebug('sse-onopen', { readyState: eventSource.readyState });
            };
	            
            eventSource.onmessage = (event) => {
                try {
                    lastStreamSeenAt = Date.now();
                    const data = JSON.parse(event.data);
                    if (data.type === 'heartbeat') {
                        pushStreamDebug('sse-heartbeat', { ts: data.ts || '' });
                        return;
                    }
                    const runId = String(data.run_id || '__default__');
                    const requestId = String(data.request_id || '');
                    const eventSessionId = String(data.session_id || activeSessionId.value || '');
                    pushStreamDebug('sse-message', {
                        type: data.type || '',
                        state: data.state || '',
                        run_id: runId,
                        request_id: requestId,
                        session_id: eventSessionId,
                        content_len: typeof data.content === 'string' ? data.content.length : 0,
                    });

                    const updateTypingState = () => {
                        syncStreamActivityState();
                        isTyping.value = activeSessionRunning.value || (submitInFlight.value && !activeSessionId.value);
                    };

                    const flushRun = (rid) => {
                        const st = runStates.get(rid);
                        if (!st) return;
                        const buf = st.buffer;
                        if (!buf) return;
                        st.buffer = '';
                        let totalLen = 0;
                        let renderedLen = 0;
                        updateSessionMessage(st.sessionId, st.assistantIndex, (msg) => {
                            if (!msg || msg.role !== 'assistant') return;
                            if (Array.isArray(msg.parts)) msg.parts.push(buf);
                            msg.totalLen = (msg.totalLen || 0) + buf.length;
                            if (msg.totalLen <= streamViewMax) {
                                msg.content += buf;
                            } else {
                                msg.tail = (String(msg.tail || '') + buf).slice(-streamTailMax);
                                msg.content = `【输出过长，流式仅显示末尾 ${streamTailMax} 字】\n` + msg.tail;
                            }
                            totalLen = msg.totalLen;
                            renderedLen = msg.content.length;
                        });
                        pushStreamDebug('flush-run', {
                            run_id: rid,
                            flushed_len: buf.length,
                            total_len: totalLen,
                            rendered_len: renderedLen,
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
                        const sid = eventSessionId || activeSessionId.value;
                        pushSessionMessage(sid, makeMessage('user', data.content, {
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
                        const assistantIndex = pushSessionMessage(sid, makeMessage('assistant', '', { streaming: true, run_id: runId }));
                        runStates.set(runId, { sessionId: sid, assistantIndex, buffer: '', flushTimer: null });
                        updateRunningSession(sid, true);
                        updateTypingState();
                    } else if (data.type === 'system') {
                        pushSessionMessage(eventSessionId, makeMessage('assistant', data.content || '', {
                            timestamp: data.timestamp || new Date().toLocaleTimeString(),
                            source: data.source || 'system'
                        }));
                        scrollToBottom();
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
                        const msg = (sessionMessages.value[st.sessionId] || [])[st.assistantIndex];
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
                            updateRunningSession(eventSessionId, false);
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
                        const msg = (sessionMessages.value[st.sessionId] || [])[st.assistantIndex];
                        if (msg && msg.role === 'assistant') {
                            const full = (data.content !== undefined && data.content !== null && String(data.content) !== '')
                                ? String(data.content)
                                : (Array.isArray(msg.parts) ? msg.parts.join('') : msg.content);
                            updateSessionMessage(st.sessionId, st.assistantIndex, (m) => {
                                m.content = full;
                                m.streaming = false;
                                finalizeMessage(m);
                            });
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
                        updateRunningSession(st.sessionId, false);
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
                        updateRunningSession(eventSessionId, true);
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
                if (!sseReconnectTimer) reconnectStream('error');
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

        const ensureBackendDataLoaded = async (attempts = 20, intervalMs = 800) => {
            for (let i = 0; i < attempts; i += 1) {
                const ok = await fetchStatus();
                if (ok) {
                    await fetchWorkspace();
                    await fetchWorkspaceOptions();
                    await fetchLlmConfigs();
                    await fetchSopList();
                    await fetchCurrentConversation();
                    await fetchGoalStatus();
                    await fetchHiveStatus();
                    bootstrapLoaded = true;
                    return true;
                }
                await sleep(intervalMs);
            }
            return false;
        };

        const refreshStatusUntilModelVisible = async (configId, timeoutMs = 4000, intervalMs = 300) => {
            const start = Date.now();
            const hasConfig = () => {
                const list = status.value && status.value.llm_list;
                if (!Array.isArray(list)) return false;
                return list.some((m) => Array.isArray(m) && (m[3] === configId || String(m[1] || '').includes(configId)));
            };
            await fetchStatus();
            if (!configId) return;
            while (Date.now() - start < timeoutMs) {
                if (hasConfig()) return;
                await new Promise((r) => setTimeout(r, intervalMs));
                await fetchStatus();
            }
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
                await fetchStatus();
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

        const handleCompositionStart = () => {
            isComposing.value = true;
        };

        const handleCompositionEnd = () => {
            isComposing.value = false;
        };

        const handleInputKeydown = (event) => {
            if (event.key !== 'Enter' || event.shiftKey) return;
            if (event.isComposing || isComposing.value || event.keyCode === 229) return;
            event.preventDefault();
            sendMessage();
        };

        const applyModeCommand = (mode) => {
            if (!mode || !mode.id) return;
            if (selectedModeIds.value.includes(mode.id)) {
                selectedModeIds.value = selectedModeIds.value.filter((id) => id !== mode.id);
            } else if (mode.id === 'goal') {
                pendingGoalMode.value = mode;
                return;
            } else {
                selectedModeIds.value = [...selectedModeIds.value, mode.id];
            }
            nextTick(() => {
                const textarea = document.querySelector('textarea');
                if (textarea) {
                    textarea.focus();
                }
            });
        };

        const confirmGoalMode = () => {
            const mode = pendingGoalMode.value;
            pendingGoalMode.value = null;
            if (mode && !selectedModeIds.value.includes(mode.id)) {
                selectedModeIds.value = [...selectedModeIds.value, mode.id];
            }
            nextTick(() => {
                const textarea = document.querySelector('textarea');
                if (textarea) textarea.focus();
            });
        };

        const cancelGoalMode = () => {
            pendingGoalMode.value = null;
        };

        const handleInputCommand = () => {
            const raw = String(inputMessage.value || '');
            const trimmed = raw.trimStart();
            const cmd = modeCommands.find((m) => trimmed === m.label || trimmed.startsWith(m.label + ' '));
            if (!cmd && !selectedModeCommands.value.length) return raw;
            if (!cmd) return `${selectedModeCommands.value.map((mode) => mode.prompt).join('\n\n')}\n\n${raw}`;
            const rest = trimmed.slice(cmd.label.length).trim();
            return rest ? `${cmd.prompt}\n\n${rest}` : cmd.prompt;
        };

        const readImageFile = (file) => new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve({
                id: `${Date.now()}_${Math.random().toString(16).slice(2)}`,
                name: file.name || 'image.png',
                type: file.type || 'image/png',
                size: file.size || 0,
                dataUrl: String(reader.result || '')
            });
            reader.onerror = () => reject(reader.error || new Error('read image failed'));
            reader.readAsDataURL(file);
        });

        const addImageFiles = async (files) => {
            const list = Array.from(files || []).filter((file) => file && String(file.type || '').startsWith('image/'));
            if (!list.length) return;
            attachmentError.value = '';
            try {
                const remaining = Math.max(0, 12 - attachedImages.value.length);
                const images = await Promise.all(list.slice(0, remaining).map(readImageFile));
                attachedImages.value = [...attachedImages.value, ...images].slice(0, 12);
                nextTick(() => { if (window.lucide) lucide.createIcons(); });
            } catch (e) {
                attachmentError.value = String(e && e.message ? e.message : e);
            }
        };

        const triggerImagePicker = () => {
            if (fileInputRef.value) fileInputRef.value.click();
        };

        const handleImagePicker = async (event) => {
            await addImageFiles(event && event.target ? event.target.files : []);
            if (event && event.target) event.target.value = '';
        };

        const removeAttachedImage = (id) => {
            attachedImages.value = attachedImages.value.filter((img) => img.id !== id);
        };

        const clearAttachedImages = () => {
            attachedImages.value = [];
            attachmentError.value = '';
        };

        const handleInputPaste = async (event) => {
            const items = event && event.clipboardData ? Array.from(event.clipboardData.items || []) : [];
            const files = items
                .filter((item) => item.kind === 'file' && String(item.type || '').startsWith('image/'))
                .map((item) => item.getAsFile())
                .filter(Boolean);
            if (files.length) {
                event.preventDefault();
                await addImageFiles(files);
            }
        };

        const handleInputDrop = async (event) => {
            const files = event && event.dataTransfer ? Array.from(event.dataTransfer.files || []) : [];
            if (files.some((file) => String(file.type || '').startsWith('image/'))) {
                event.preventDefault();
                await addImageFiles(files);
            }
        };

        const uploadAttachedImages = async () => {
            if (!attachedImages.value.length) return [];
            attachmentUploading.value = true;
            attachmentError.value = '';
            try {
                const res = await fetch('/api/uploads/images', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        images: attachedImages.value.map((img) => ({
                            id: img.id,
                            name: img.name,
                            type: img.type,
                            dataUrl: img.dataUrl
                        }))
                    })
                });
                const data = await res.json().catch(() => ({}));
                if (!res.ok || data.error) throw new Error(data.error || `HTTP ${res.status}`);
                return Array.isArray(data.images) ? data.images : [];
            } finally {
                attachmentUploading.value = false;
            }
        };

        const sendMessage = async () => {
            if ((!inputMessage.value.trim() && !attachedImages.value.length) || activeSessionRunning.value) return;

            const prompt = handleInputCommand();
            await submitPrompt(prompt || '请分析这张图片。', { clearInput: true, resetModes: true });
        };

        const submitPrompt = async (prompt, options = {}) => {
            if ((!String(prompt || '').trim() && !attachedImages.value.length) || activeSessionRunning.value) return;
            if (!activeSessionId.value) {
                await fetchSessions();
                if (!activeSessionId.value) await createChatSession();
            }
            const sessionId = activeSessionId.value;
            if (!sessionId) {
                attachmentError.value = '还没有可用的对话 session';
                return;
            }

            const requestId = (typeof crypto !== 'undefined' && crypto.randomUUID)
                ? crypto.randomUUID()
                : `${Date.now()}_${Math.random().toString(16).slice(2)}`;
            currentSubmitAbortController = new AbortController();
            submitInFlight.value = true;
            submissionNotice.value = '正在提交到后端...';
            pushStreamDebug('send-start', {
                request_id: requestId,
                session_id: sessionId,
                prompt_len: prompt.length,
                run_states: runStates.size,
                active_runs: activeStreamRuns,
            });

            // Reset textarea height immediately, but keep the text until the backend acks it.
            const textarea = document.querySelector('textarea');
            if (textarea) textarea.style.height = '3.5rem';

            try {
                const uploadedImages = await uploadAttachedImages();
                const response = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}/chat`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ prompt, request_id: requestId, images: uploadedImages }),
                    signal: currentSubmitAbortController.signal
                });

                const data = await response.json().catch(() => ({}));
                if (!response.ok || (data && data.error)) throw new Error((data && data.error) ? data.error : 'Network response was not ok');

                const runId = String(data.run_id || '');
                pendingSubmissions.set(requestId, {
                    request_id: requestId,
                    run_id: runId,
                    session_id: sessionId,
                    prompt_len: prompt.length,
                    confirmed: false,
                    startedAt: Date.now(),
                });
                // 移除状态提示
                pushStreamDebug('send-queued', {
                    request_id: requestId,
                    run_id: runId,
                    session_id: sessionId,
                    status: response.status,
                });

                if (options.clearInput !== false) inputMessage.value = '';
                if (options.clearInput !== false) clearAttachedImages();
                if (options.resetModes !== false) selectedModeIds.value = [];
                submitInFlight.value = false;
                currentSubmitAbortController = null;
                updateRunningSession(sessionId, true);
                isTyping.value = activeSessionRunning.value;
                status.value.is_running = true;
                status.value.needs_human_input = false;
                setFloatingStateHint('running', 30000);
                emitFloatingStatus(status.value, true, 'running');
            } catch (e) {
                const aborted = e && (e.name === 'AbortError' || String(e).includes('aborted'));
                console.error('Send failed:', e);
                submitInFlight.value = false;
                currentSubmitAbortController = null;
                if (!aborted) attachmentError.value = String(e && e.message ? e.message : e);
                submissionNotice.value = aborted ? '已放弃当前等待' : '提交失败：' + e.message;
                updateRunningSession(sessionId, false);
                status.value.is_running = false;
                setFloatingStateHint('idle');
                emitFloatingStatus(status.value, false, 'error');
                isTyping.value = activeSessionRunning.value;
            }
        };

        const renderMarkdown = (text) => {
            return safeRenderMarkdown(text || '');
        };

        const normalizeHistoryContent = (content) => {
            if (Array.isArray(content)) {
                const parts = [];
                for (const block of content) {
                    if (typeof block === 'string') {
                        parts.push(block);
                        continue;
                    }
                    if (block && typeof block === 'object') {
                        if (typeof block.text === 'string') parts.push(block.text);
                        else if (typeof block.content === 'string') parts.push(block.content);
                        else {
                            try {
                                parts.push(JSON.stringify(block, null, 2));
                            } catch (e) {}
                        }
                    }
                }
                return parts.join('\n');
            }
            if (content && typeof content === 'object') {
                try {
                    return JSON.stringify(content, null, 2);
                } catch (e) {
                    return String(content);
                }
            }
            return String(content ?? '');
        };

        const normalizeHistoryMessage = (item, index) => {
            const role = String((item && (item.role || item.speaker || item.name)) || 'entry');
            const timestamp = String((item && (item.timestamp || item.time || item.created_at)) || '');
            const content = normalizeHistoryContent(item && item.content !== undefined ? item.content : item);
            return {
                id: item && item.id ? String(item.id) : `history-message-${index}`,
                role,
                timestamp,
                content,
                html: renderMarkdown(content)
            };
        };

        const historySessionView = computed(() => Array.isArray(historySessions.value) ? historySessions.value : []);
        const historyMessageView = computed(() => historyMessages.value.map((item, index) => normalizeHistoryMessage(item, index)));
        const historySearchResultView = computed(() => Array.isArray(historySearchResults.value) ? historySearchResults.value : []);

        const memoryFilesView = computed(() => Array.isArray(memoryFiles.value) ? memoryFiles.value : []);

        const formatTokenCount = (value) => {
            const n = Number(value) || 0;
            if (n >= 1000000) return `${(n / 1000000).toFixed(n >= 10000000 ? 0 : 1)}M`;
            if (n >= 1000) return `${(n / 1000).toFixed(n >= 10000 ? 0 : 1)}K`;
            return String(n);
        };

        const tokenUsage = computed(() => {
            const usage = status.value && status.value.token_usage;
            return usage && usage.available ? usage : null;
        });

        const tokenUsageLabel = computed(() => {
            const usage = tokenUsage.value;
            if (!usage || !usage.total) return '0 tokens';
            return `${formatTokenCount(usage.total)} tokens`;
        });

        const tokenContextPercent = computed(() => {
            const usage = tokenUsage.value;
            const limit = Number(usage && usage.context_limit_chars) || 0;
            const current = Number(usage && usage.context_chars) || 0;
            if (!limit || !current) return 0;
            return Math.max(0, Math.min(100, Math.round((current / limit) * 100)));
        });

        const canIntervene = computed(() => {
            if (interventionSaving.value) return false;
            return true;
        });

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
            if (name === 'orchestration') {
                openOrchestrationConsole();
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
                if (name === 'communication') await fetchCommunicationConfigs();
                if (name === 'todo') await fetchToDo();
                if (name === 'sop') await fetchSopList();
                if (name === 'schedule') await refreshScheduleList();
                if (name === 'history') await fetchHistoryData();
                if (name === 'memory') await fetchMemoryList();
                if (name === 'backup') await fetchBackups();
                if (name === 'orchestration') {
                    await fetchGoalStatus();
                    await fetchHiveStatus();
                    await fetchHivePosts();
                }
                if (name === 'pet') {
                    await fetchPetSkins();
                    await fetchPetConfig();
                }
                if (name === 'workspace') {
                    await fetchWorkspace();
                    await fetchWorkspaceOptions();
                }
            } finally {
                nextTick(() => {
                    if (window.lucide) lucide.createIcons();
                });
            }
        };

        const refreshOrchestrationPanel = async () => {
            const tasks = [
                fetchGoalStatus().catch((e) => {
                    goalError.value = String(e && e.message ? e.message : e);
                    return false;
                }),
                fetchHiveStatus().catch((e) => {
                    hiveError.value = String(e && e.message ? e.message : e);
                    return false;
                }),
                fetchHivePosts().catch((e) => {
                    hivePostsError.value = String(e && e.message ? e.message : e);
                    return false;
                }),
            ];
            await Promise.allSettled(tasks);
        };

        const openOrchestrationConsole = () => {
            activeModal.value = 'orchestration';
            orchestrationTab.value = 'hive';
            nextTick(() => {
                if (window.lucide) lucide.createIcons();
            });
            refreshOrchestrationPanel();
        };

        const closeModal = () => {
            activeModal.value = '';
            keyEditorOpen.value = false;
        };

        const fetchLlmConfigs = async () => {
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
                keyEditorNotice.value = out && out.url ? `API 测试通过：${out.url}` : 'API 测试通过';
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
                const out = await res.json();
                const targetId = out && out.id ? out.id : '';
                if (out && Array.isArray(out.configs)) {
                    llmConfigs.value = out.configs;
                }
                if (out && Array.isArray(out.llm_list)) {
                    status.value = { ...status.value, llm_list: out.llm_list };
                }
                if (out && out.agent_init_error) {
                    keyEditorError.value = out.agent_init_error;
                    return;
                }
                await fetchLlmConfigs();
                if (targetId && !llmConfigs.value.some((c) => c.id === targetId)) {
                    llmConfigs.value = [
                        ...llmConfigs.value,
                        {
                            id: targetId,
                            type: editType.value,
                            apibase: editApiBase.value || '',
                            model: editModel.value || '',
                            has_key: true,
                            key_last4: String(editApiKey.value || '').slice(-4)
                        }
                    ];
                }
                keyEditorNotice.value = '已保存并完成重载';
                await refreshStatusUntilModelVisible(targetId);
                
                // Automatically switch to the newly saved model
                if (targetId && status.value && status.value.llm_list) {
                    const idx = status.value.llm_list.findIndex(m => Array.isArray(m) && (m[3] === targetId || String(m[1] || '').includes(targetId)));
                    if (idx >= 0) {
                        await switchLLM(idx);
                    }
                }

                await fetchLlmConfigs();
                await fetchStatus();
                closeKeyEditor();
            } catch (e) {
                console.error('Save llm config failed:', e);
                keyEditorError.value = String(e && e.message ? e.message : e);
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
                await refreshStatusUntilModelVisible('');
                closeKeyEditor();
            } catch (e) {
                console.error('Delete llm config failed:', e);
            }
        };

        const fetchToDo = async () => {
            try {
                const res = await fetch('/api/todo');
                if (!res.ok) return;
                const data = await res.json();
                todoContent.value = data.content || '';
            } catch (e) {
                console.error('Fetch todo failed:', e);
            }
        };

        const fetchHistoryData = async () => {
            historyLoading.value = true;
            historyError.value = '';
            historyNotice.value = '';
            try {
                const res = await fetch('/api/conversations');
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                const data = await res.json();
                historySessions.value = Array.isArray(data.sessions) ? data.sessions : [];
                const keep = selectedHistorySessionId.value && historySessions.value.some((item) => item.session_id === selectedHistorySessionId.value);
                const next = keep
                    ? selectedHistorySessionId.value
                    : ((historySessions.value.find((item) => item.current) || historySessions.value[0] || {}).session_id || '');
                if (next) await selectHistorySession(next);
                else {
                    selectedHistorySessionId.value = '';
                    selectedHistorySession.value = null;
                    historyMessages.value = [];
                }
            } catch (e) {
                historyError.value = String(e && e.message ? e.message : e);
            } finally {
                historyLoading.value = false;
            }
        };

        const refreshHistoryData = async () => {
            await fetchHistoryData();
        };

        let historySearchTimer = null;
        const searchHistory = async () => {
            const q = String(historySearchQuery.value || '').trim();
            historySearchError.value = '';
            if (!q) {
                historySearchResults.value = [];
                return;
            }
            historySearchLoading.value = true;
            try {
                const url = `/api/conversations/search?q=${encodeURIComponent(q)}&limit=50`;
                const res = await fetch(url);
                const data = await res.json().catch(() => ({}));
                if (!res.ok || data.error) throw new Error(data.error || `HTTP ${res.status}`);
                historySearchResults.value = Array.isArray(data.results) ? data.results : [];
            } catch (e) {
                historySearchError.value = String(e && e.message ? e.message : e);
            } finally {
                historySearchLoading.value = false;
            }
        };

        const scheduleHistorySearch = () => {
            if (historySearchTimer) clearTimeout(historySearchTimer);
            historySearchTimer = setTimeout(searchHistory, 250);
        };

        watch(historySearchQuery, scheduleHistorySearch);

        const selectHistorySession = async (sessionId) => {
            if (!sessionId) return;
            selectedHistorySessionId.value = sessionId;
            historyError.value = '';
            try {
                const res = await fetch(`/api/conversations/${encodeURIComponent(sessionId)}`);
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                const data = await res.json();
                selectedHistorySession.value = data;
                historyMessages.value = Array.isArray(data.messages) ? data.messages : [];
                historyTitleDraft.value = data.title || '';
            } catch (e) {
                historyError.value = String(e && e.message ? e.message : e);
            }
        };

        const renameHistorySession = async () => {
            const sessionId = selectedHistorySessionId.value;
            const title = String(historyTitleDraft.value || '').trim();
            if (!sessionId || !title) return;
            historySavingTitle.value = true;
            historyError.value = '';
            historyNotice.value = '';
            try {
                const res = await fetch(`/api/conversations/${encodeURIComponent(sessionId)}/rename`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ title })
                });
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                historyNotice.value = '已更新会话名称';
                await fetchHistoryData();
            } catch (e) {
                historyError.value = String(e && e.message ? e.message : e);
            } finally {
                historySavingTitle.value = false;
            }
        };

        const exportHistorySession = (sessionId = selectedHistorySessionId.value) => {
            if (!sessionId) return;
            window.open(`/api/conversations/${encodeURIComponent(sessionId)}/export`, '_blank');
        };

        const restoreHistorySession = async (sessionId = selectedHistorySessionId.value) => {
            if (!sessionId) return;
            historyLoading.value = true;
            historyError.value = '';
            historyNotice.value = '';
            try {
                const res = await fetch(`/api/conversations/${encodeURIComponent(sessionId)}/restore`, { method: 'POST' });
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                await fetchCurrentConversation();
                await fetchStatus();
                activeModal.value = '';
                historyNotice.value = '已恢复到当前对话';
            } catch (e) {
                historyError.value = String(e && e.message ? e.message : e);
            } finally {
                historyLoading.value = false;
            }
        };

        const fetchMemoryList = async () => {
            memoryLoading.value = true;
            memoryError.value = '';
            try {
                const res = await fetch('/api/memory/list');
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                const data = await res.json();
                memoryRoot.value = data.root || '';
                memoryFiles.value = Array.isArray(data.files) ? data.files : [];
                if (!selectedMemoryFile.value && memoryFiles.value.length) {
                    await selectMemoryFile(memoryFiles.value[0].name);
                }
            } catch (e) {
                memoryError.value = String(e && e.message ? e.message : e);
            } finally {
                memoryLoading.value = false;
            }
        };

        const selectMemoryFile = async (name) => {
            if (!name) return;
            selectedMemoryFile.value = name;
            memoryContent.value = '';
            memoryError.value = '';
            try {
                const res = await fetch(`/api/memory/read?name=${encodeURIComponent(name)}`);
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                const data = await res.json();
                memoryContent.value = data.content || '';
            } catch (e) {
                memoryError.value = String(e && e.message ? e.message : e);
            }
        };

        const refreshMemoryList = async () => {
            await fetchMemoryList();
        };

        const memoryFileIsMarkdown = computed(() => {
            return /\.(md|markdown)$/i.test(selectedMemoryFile.value || '');
        });

        const formatBackupSize = (bytes) => {
            const n = Number(bytes) || 0;
            if (n < 1024) return `${n} B`;
            if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
            return `${(n / 1024 / 1024).toFixed(1)} MB`;
        };

        const fetchBackups = async () => {
            backupLoading.value = true;
            backupError.value = '';
            try {
                const res = await fetch('/api/backups');
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                const data = await res.json();
                backupRoot.value = data.root || '';
                backupItems.value = Array.isArray(data.items) ? data.items : [];
            } catch (e) {
                backupError.value = String(e && e.message ? e.message : e);
            } finally {
                backupLoading.value = false;
            }
        };

        const createBackup = async () => {
            backupCreating.value = true;
            backupNotice.value = '';
            backupError.value = '';
            try {
                const res = await fetch('/api/backups/create', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ reason: 'manual-ui' })
                });
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                const data = await res.json();
                backupItems.value = data.list && Array.isArray(data.list.items) ? data.list.items : backupItems.value;
                backupRoot.value = data.list && data.list.root ? data.list.root : backupRoot.value;
                backupNotice.value = `已创建备份：${data.backup && data.backup.backup_dir ? data.backup.backup_dir : ''}`;
            } catch (e) {
                backupError.value = String(e && e.message ? e.message : e);
            } finally {
                backupCreating.value = false;
            }
        };

        const formatGoalMinutes = (seconds) => {
            const n = Math.max(0, Number(seconds) || 0);
            if (n < 60) return `${Math.round(n)} 秒`;
            const minutes = Math.round(n / 60);
            if (minutes < 60) return `${minutes} 分钟`;
            const hours = Math.floor(minutes / 60);
            const rest = minutes % 60;
            return rest ? `${hours} 小时 ${rest} 分钟` : `${hours} 小时`;
        };

        const fetchGoalStatus = async () => {
            goalLoading.value = true;
            goalError.value = '';
            try {
                const res = await fetch('/api/goal/status');
                const data = await res.json().catch(() => ({}));
                if (!res.ok || data.error) throw new Error(data.error || `HTTP ${res.status}`);
                goalState.value = data;
                return true;
            } catch (e) {
                goalError.value = String(e && e.message ? e.message : e);
                return false;
            } finally {
                goalLoading.value = false;
            }
        };

        const startGoalMode = async () => {
            const objective = String(goalObjective.value || '').trim();
            if (!objective) {
                goalError.value = '请先填写目标';
                return;
            }
            goalLoading.value = true;
            goalError.value = '';
            goalNotice.value = '';
            try {
                const res = await fetch('/api/goal/start', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        objective,
                        budget_minutes: Number(goalBudgetMinutes.value) || 30,
                        max_turns: Number(goalMaxTurns.value) || 80,
                        done_prompt: goalDonePrompt.value || ''
                    })
                });
                const data = await res.json().catch(() => ({}));
                if (!res.ok || data.error) throw new Error(data.error || `HTTP ${res.status}`);
                goalState.value = data;
                goalNotice.value = 'Goal 模式已在后台启动';
            } catch (e) {
                goalError.value = String(e && e.message ? e.message : e);
            } finally {
                goalLoading.value = false;
            }
        };

        const stopGoalMode = async () => {
            goalLoading.value = true;
            goalError.value = '';
            goalNotice.value = '';
            try {
                const res = await fetch('/api/goal/stop', { method: 'POST' });
                const data = await res.json().catch(() => ({}));
                if (!res.ok || data.error) throw new Error(data.error || `HTTP ${res.status}`);
                goalState.value = data;
                goalNotice.value = 'Goal 模式已停止';
            } catch (e) {
                goalError.value = String(e && e.message ? e.message : e);
            } finally {
                goalLoading.value = false;
            }
        };

        const fetchHiveStatus = async () => {
            hiveLoading.value = true;
            hiveError.value = '';
            try {
                const res = await fetch('/api/hive/status');
                const data = await res.json().catch(() => ({}));
                if (!res.ok || data.error) throw new Error(data.error || `HTTP ${res.status}`);
                hiveState.value = data;
                return true;
            } catch (e) {
                hiveError.value = String(e && e.message ? e.message : e);
                return false;
            } finally {
                hiveLoading.value = false;
            }
        };

        const fetchHivePosts = async () => {
            hivePostsLoading.value = true;
            hivePostsError.value = '';
            try {
                const res = await fetch('/api/hive/posts?limit=80');
                const data = await res.json().catch(() => ({}));
                if (!res.ok || data.error) {
                    if (data.error) hivePostsError.value = data.error;
                    else throw new Error(`HTTP ${res.status}`);
                }
                hiveBbsOffline.value = !!data.offline;
                if (data.offline) hivePostsError.value = '';
                hivePosts.value = Array.isArray(data.posts) ? data.posts : [];
                hiveBbsUrl.value = data.bbs_url || '';
                return true;
            } catch (e) {
                const msg = String(e && e.message ? e.message : e);
                if (msg.includes('Connection refused') || msg.includes('Errno 61')) {
                    hiveBbsOffline.value = true;
                    hivePostsError.value = '';
                } else {
                    hivePostsError.value = msg;
                }
                return false;
            } finally {
                hivePostsLoading.value = false;
            }
        };

        const switchOrchestrationTab = async (tab) => {
            orchestrationTab.value = tab === 'hive' ? 'hive' : 'goal';
            if (orchestrationTab.value === 'hive') {
                await fetchHiveStatus();
                await fetchHivePosts();
            } else {
                await fetchGoalStatus();
            }
        };

        const refreshHivePanel = async () => {
            await fetchHiveStatus();
            await fetchHivePosts();
        };

        const hiveStatusLabel = (state) => {
            const s = state || hiveState.value || {};
            const effective = s.effective_status || (s.state && s.state.status) || '';
            if (s.master_status === 'done_budget') return s.worker_pids && s.worker_pids.length ? 'Master已结束，Worker收尾中' : '预算结束';
            if (effective === 'workers_running') return 'Worker收尾中';
            if (String(effective).startsWith('bbs_only_')) return '仅BBS在线';
            if (s.active_coordination) return '协作中';
            if (effective) return effective;
            return '未启动';
        };

        const hiveStatusDotClass = (state) => {
            const s = state || hiveState.value || {};
            if (s.active_coordination) return 'bg-green-500 animate-pulse';
            if (s.bbs_running) return 'bg-amber-500';
            return 'bg-gray-400';
        };

        const hivePostRole = (post) => {
            const author = String(post && post.author ? post.author : '').toLowerCase();
            if (author.includes('master')) return 'master';
            if (author.includes('worker')) return 'worker';
            if (author.includes('human') || author.includes('user')) return 'human';
            if (author.includes('seed') || author.includes('system')) return 'system';
            return 'agent';
        };

        const hivePostRoleLabel = (post) => {
            const role = hivePostRole(post);
            if (role === 'master') return 'MASTER';
            if (role === 'worker') return 'WORKER';
            if (role === 'human') return 'HUMAN';
            if (role === 'system') return 'SYSTEM';
            return 'AGENT';
        };

        const hivePostRoleClass = (post) => {
            const role = hivePostRole(post);
            if (role === 'master') return 'bg-indigo-50 text-indigo-700 border-indigo-200 dark:bg-indigo-950 dark:text-indigo-200 dark:border-indigo-800';
            if (role === 'worker') return 'bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950 dark:text-emerald-200 dark:border-emerald-800';
            if (role === 'human') return 'bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950 dark:text-amber-200 dark:border-amber-800';
            if (role === 'system') return 'bg-gray-100 text-gray-700 border-gray-200 dark:bg-gray-800 dark:text-gray-200 dark:border-gray-700';
            return 'bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-950 dark:text-blue-200 dark:border-blue-800';
        };

        const formatHivePostTime = (post) => {
            const ts = Number(post && post.created_at ? post.created_at : 0);
            if (!Number.isFinite(ts) || ts <= 0) return '';
            const date = new Date(ts * 1000);
            return date.toLocaleString([], {
                month: '2-digit',
                day: '2-digit',
                hour: '2-digit',
                minute: '2-digit'
            });
        };

        const formatHiveDuration = (seconds) => {
            if (seconds === null || seconds === undefined || seconds === '') return '-';
            const n = Math.max(0, Math.floor(Number(seconds) || 0));
            const m = Math.floor(n / 60);
            const s = n % 60;
            if (m >= 60) {
                const h = Math.floor(m / 60);
                const mm = m % 60;
                return `${h}h ${mm}m`;
            }
            return `${m}:${String(s).padStart(2, '0')}`;
        };

        const hivePostPreview = (post) => {
            const text = String(post && post.content ? post.content : '');
            return text.length > 220 ? `${text.slice(0, 220)}...` : text;
        };

        const hivePostExpanded = (post) => !!(post && hiveExpandedPosts.value[post.id]);

        const toggleHivePostExpanded = (post) => {
            if (!post) return;
            hiveExpandedPosts.value = { ...hiveExpandedPosts.value, [post.id]: !hiveExpandedPosts.value[post.id] };
        };

        const hiveControlAgent = async (action) => {
            hiveLoading.value = true;
            hiveError.value = '';
            hiveNotice.value = '';
            try {
                const res = await fetch('/api/hive/control', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ action, target: hiveControlTarget.value || 'all' })
                });
                const data = await res.json().catch(() => ({}));
                if (!res.ok || data.error) throw new Error(data.error || `HTTP ${res.status}`);
                hiveState.value = data;
                const label = action === 'pause' ? '暂停' : (action === 'resume' ? '继续' : '停止');
                hiveNotice.value = `已${label} ${data.changed && data.changed.length ? data.changed.join(', ') : hiveControlTarget.value}`;
                await fetchHivePosts();
            } catch (e) {
                hiveError.value = String(e && e.message ? e.message : e);
            } finally {
                hiveLoading.value = false;
            }
        };

        const extendHiveBudget = async () => {
            hiveLoading.value = true;
            hiveError.value = '';
            hiveNotice.value = '';
            try {
                const res = await fetch('/api/hive/extend', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        minutes: Number(hiveExtendMinutes.value) || 0,
                        turns: Number(hiveExtendTurns.value) || 0
                    })
                });
                const data = await res.json().catch(() => ({}));
                if (!res.ok || data.error) throw new Error(data.error || `HTTP ${res.status}`);
                hiveState.value = data;
                hiveNotice.value = '已追加 Hive 预算';
                await fetchHivePosts();
            } catch (e) {
                hiveError.value = String(e && e.message ? e.message : e);
            } finally {
                hiveLoading.value = false;
            }
        };

        const postHiveMessage = async () => {
            const content = String(hivePostContent.value || '').trim();
            if (!content) return;
            hivePosting.value = true;
            hivePostsError.value = '';
            try {
                const res = await fetch('/api/hive/post', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        author: hivePostAuthor.value || 'human',
                        content
                    })
                });
                const data = await res.json().catch(() => ({}));
                if (!res.ok || data.error) throw new Error(data.error || `HTTP ${res.status}`);
                hivePostContent.value = '';
                await fetchHivePosts();
            } catch (e) {
                hivePostsError.value = String(e && e.message ? e.message : e);
            } finally {
                hivePosting.value = false;
            }
        };

        const appendHiveMention = (mention) => {
            const prefix = String(mention || '').trim();
            if (!prefix) return;
            const current = String(hivePostContent.value || '');
            if (current.trim().startsWith(prefix)) return;
            hivePostContent.value = current.trim() ? `${prefix} ${current}` : `${prefix} `;
        };

        const startHiveMode = async () => {
            const objective = String(hiveObjective.value || '').trim();
            if (!objective) {
                hiveError.value = '请先填写 Hive 目标';
                return;
            }
            hiveLoading.value = true;
            hiveError.value = '';
            hiveNotice.value = '';
            try {
                const res = await fetch('/api/hive/start', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        objective,
                        budget_minutes: Number(hiveBudgetMinutes.value) || 30,
                        max_turns: Number(hiveMaxTurns.value) || 80,
                        worker_count: Number(hiveWorkerCount.value) || 2
                    })
                });
                const data = await res.json().catch(() => ({}));
                if (!res.ok || data.error) throw new Error(data.error || `HTTP ${res.status}`);
                hiveState.value = data;
                hiveNotice.value = 'Hive 模式已启动';
                await fetchHivePosts();
            } catch (e) {
                hiveError.value = String(e && e.message ? e.message : e);
            } finally {
                hiveLoading.value = false;
            }
        };

        const stopHiveMode = async () => {
            hiveLoading.value = true;
            hiveError.value = '';
            hiveNotice.value = '';
            try {
                const res = await fetch('/api/hive/stop', { method: 'POST' });
                const data = await res.json().catch(() => ({}));
                if (!res.ok || data.error) throw new Error(data.error || `HTTP ${res.status}`);
                hiveState.value = data;
                hiveNotice.value = 'Hive 模式已停止';
                await fetchHivePosts();
            } catch (e) {
                hiveError.value = String(e && e.message ? e.message : e);
            } finally {
                hiveLoading.value = false;
            }
        };

        const fetchCommunicationConfigs = async () => {
            communicationLoading.value = true;
            communicationError.value = '';
            communicationNotice.value = '';
            try {
                const res = await fetch('/api/communication_configs');
                const data = await res.json().catch(() => ({}));
                if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
                communicationTools.value = Array.isArray(data.tools) ? data.tools : [];
                communicationPath.value = data.path || '';
                const drafts = { ...communicationDrafts.value };
                for (const tool of communicationTools.value) {
                    const current = drafts[tool.id] || {};
                    drafts[tool.id] = {
                        app_id: tool.app_id || current.app_id || '',
                        secret: '',
                        allowed_users: Array.isArray(tool.allowed_users) ? tool.allowed_users.join('\n') : (current.allowed_users || '')
                    };
                }
                communicationDrafts.value = drafts;
                if (communicationTools.value.length) {
                    const current = communicationTools.value.find((tool) => tool.id === selectedCommunicationId.value) || communicationTools.value[0];
                    selectedCommunicationId.value = current.id;
                } else {
                    selectedCommunicationId.value = '';
                }
                return true;
            } catch (e) {
                communicationError.value = String(e && e.message ? e.message : e);
                return false;
            } finally {
                communicationLoading.value = false;
            }
        };

        const selectedCommunicationTool = computed(() => {
            return communicationTools.value.find((tool) => tool.id === selectedCommunicationId.value) || null;
        });

        const selectCommunicationTool = (toolId) => {
            selectedCommunicationId.value = toolId || '';
            communicationNotice.value = '';
            communicationError.value = '';
        };

        const communicationDraft = (tool) => {
            if (!tool) return { app_id: '', secret: '', allowed_users: '' };
            return communicationDrafts.value[tool.id] || { app_id: '', secret: '', allowed_users: '' };
        };

        const communicationStatusClass = (statusName) => {
            if (statusName === 'ok') return 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300';
            if (statusName === 'failed') return 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300';
            return 'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-300';
        };

        const communicationStatusText = (statusName) => {
            if (statusName === 'ok') return '运行中';
            if (statusName === 'failed') return '已配置，未启动';
            return '未配置';
        };

        const saveCommunicationConfig = async (tool = null) => {
            const target = tool || selectedCommunicationTool.value;
            if (!target || communicationSaving.value) return false;
            const draft = communicationDraft(target);
            communicationSaving.value = true;
            communicationBusyId.value = target.id;
            communicationError.value = '';
            communicationNotice.value = '';
            try {
                const res = await fetch('/api/communication_configs/upsert', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        id: target.id,
                        app_id: draft.app_id || '',
                        secret: draft.secret || '',
                        allowed_users: draft.allowed_users || ''
                    })
                });
                const data = await res.json().catch(() => ({}));
                if (!res.ok) throw new Error(data.error || '保存失败');
                communicationNotice.value = `已保存 ${target.label} 配置`;
                await fetchCommunicationConfigs();
                return true;
            } catch (e) {
                communicationError.value = String(e && e.message ? e.message : e);
                return false;
            } finally {
                communicationSaving.value = false;
                communicationBusyId.value = '';
            }
        };

        const runCommunicationAction = async (tool, action) => {
            if (!tool || communicationBusyId.value) return;
            communicationBusyId.value = tool.id;
            communicationError.value = '';
            communicationNotice.value = '';
            try {
                if (action === 'start') {
                    const saved = await saveCommunicationConfig(tool);
                    if (!saved) return;
                    communicationBusyId.value = tool.id;
                }
                const res = await fetch('/api/communication_configs/action', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ id: tool.id, action })
                });
                const data = await res.json().catch(() => ({}));
                if (!res.ok) throw new Error(data.error || '操作失败');
                communicationNotice.value = `${tool.label}${action === 'stop' ? ' 已停止' : action === 'start' ? ' 已启动' : ' 状态已刷新'}`;
                await fetchCommunicationConfigs();
            } catch (e) {
                communicationError.value = String(e && e.message ? e.message : e);
            } finally {
                communicationBusyId.value = '';
            }
        };

        const fetchPetConfig = async () => {
            petLoading.value = true;
            petError.value = '';
            petNotice.value = '';
            try {
                const res = await fetch('/api/desktop_pet/config');
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                const data = await res.json();
                if (data.config) {
                    petConfig.value = {
                        ...petConfig.value,
                        ...data.config
                    };
                }
                petConfigPath.value = data.path || '';
            } catch (e) {
                petError.value = String(e && e.message ? e.message : e);
            } finally {
                petLoading.value = false;
            }
        };

        const fetchPetSkins = async () => {
            try {
                const res = await fetch('/api/desktop_pet/skins');
                if (!res.ok) return false;
                const data = await res.json();
                petSkins.value = Array.isArray(data.skins) ? data.skins : [];
                return true;
            } catch (e) {
                console.error('Fetch pet skins failed:', e);
                return false;
            }
        };

        const savePetConfig = async () => {
            petSaving.value = true;
            petError.value = '';
            petNotice.value = '';
            try {
                const payload = {
                    ...petConfig.value,
                    size: Number(petConfig.value.size) || 104,
                    x: petConfig.value.x === '' ? null : petConfig.value.x,
                    y: petConfig.value.y === '' ? null : petConfig.value.y
                };
                const res = await fetch('/api/desktop_pet/config', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ config: payload })
                });
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                const data = await res.json();
                if (data.config) petConfig.value = { ...petConfig.value, ...data.config };
                petConfigPath.value = data.path || petConfigPath.value;
                await Promise.all([fetchPetConfig(), fetchPetSkins()]);
                petNotice.value = '已保存并刷新，桌宠会在约 1 秒内应用新配置';
            } catch (e) {
                petError.value = String(e && e.message ? e.message : e);
            } finally {
                petSaving.value = false;
            }
        };

        const selectPetSkin = async (name) => {
            if (!name) return;
            petConfig.value.skin_name = name;
            await savePetConfig();
        };

        const deletePetSkin = async (name) => {
            if (!name || name === 'legacy-pet') return;
            if (!confirm(`确定删除桌宠形象「${name}」吗？此操作会删除对应皮肤文件。`)) return;
            petSaving.value = true;
            petError.value = '';
            petNotice.value = '';
            try {
                const res = await fetch('/api/desktop_pet/skins/delete', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name })
                });
                if (!res.ok) {
                    const data = await res.json().catch(() => ({}));
                    throw new Error(data.error || `HTTP ${res.status}`);
                }
                const data = await res.json();
                if (data.config) petConfig.value = { ...petConfig.value, ...data.config };
                petSkins.value = Array.isArray(data.skins) ? data.skins : petSkins.value.filter(skin => skin.name !== name);
                petNotice.value = '已删除桌宠形象并刷新配置';
            } catch (e) {
                petError.value = String(e && e.message ? e.message : e);
            } finally {
                petSaving.value = false;
            }
        };

        const resetPetConfig = async () => {
            petConfig.value = {
                enabled: true,
                size: 104,
                position: 'right-bottom',
                x: null,
                y: null,
                skin_name: 'legacy-pet',
                always_on_top: true,
                show_shadow: false,
                click_action: 'toggle_main'
            };
            await savePetConfig();
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
                    .filter((x) => !activeSessionId.value || x.session_id === activeSessionId.value)
                    .map((x) => x && x.run_id ? String(x.run_id) : '')
                    .filter(Boolean);
                const activeRunIds = Array.from(runStates.entries())
                    .filter(([, st]) => !activeSessionId.value || st.sessionId === activeSessionId.value)
                    .map(([rid]) => rid);
                const runIds = Array.from(new Set([...pendingRunIds, ...activeRunIds]));
                for (const [key, value] of Array.from(pendingSubmissions.entries())) {
                    if (!activeSessionId.value || value.session_id === activeSessionId.value) {
                        pendingSubmissions.delete(key);
                    }
                }
                submitInFlight.value = false;
                for (const rid of runIds) {
                    const st = runStates.get(rid);
                    if (!st) continue;
                    if (st.flushTimer) {
                        clearTimeout(st.flushTimer);
                        st.flushTimer = null;
                    }
                    updateSessionMessage(st.sessionId, st.assistantIndex, (msg) => {
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
                    });
                    runStates.delete(rid);
                }
                updateRunningSession(activeSessionId.value, false);
                isTyping.value = activeSessionRunning.value;
                submissionNotice.value = runIds.length > 0 ? '已请求停止当前任务' : '已放弃当前等待';
                setFloatingStateHint('idle');
                emitFloatingStatus(status.value, false, 'idle');
                if (activeSessionId.value) {
                    await fetch(`/api/sessions/${encodeURIComponent(activeSessionId.value)}/cancel`, { method: 'POST' });
                } else {
                    await fetch('/api/control', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ action: 'stop', run_ids: runIds })
                    });
                }
                pushStreamDebug('stop-requested', { run_ids: runIds.length });
                fetchStatus();
            } catch (e) {
                console.error('Stop task failed:', e);
            }
        };

        const newConversation = async () => {
             try {
                await createChatSession();
                renderLimit.value = 120;
                stickToBottom.value = true;
             } catch (e) {
                 console.error('New conversation failed:', e);
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

        const openIntervention = () => {
            interventionOpen.value = true;
            interventionNotice.value = '';
            interventionError.value = '';
            nextTick(() => {
                const el = document.getElementById('ga-intervention-input');
                if (el) el.focus();
            });
        };

        const closeIntervention = () => {
            if (interventionSaving.value) return;
            interventionOpen.value = false;
            interventionNotice.value = '';
            interventionError.value = '';
        };

        const submitIntervention = async () => {
            const prompt = String(interventionText.value || '').trim();
            if (!prompt || interventionSaving.value) return;
            interventionSaving.value = true;
            interventionNotice.value = '';
            interventionError.value = '';
            try {
                const res = await fetch('/api/intervene', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ prompt })
                });
                const data = await res.json().catch(() => ({}));
                if (!res.ok || data.error) throw new Error(data.error || '插入引导失败');
                interventionText.value = '';
                interventionNotice.value = '已加入一次性引导队列，下一轮读取后会自动释放';
                setTimeout(() => {
                    interventionOpen.value = false;
                    interventionNotice.value = '';
                }, 900);
                await fetchStatus();
            } catch (e) {
                interventionError.value = e && e.message ? e.message : String(e);
            } finally {
                interventionSaving.value = false;
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

        return {
            workspacePath,
            fetchWorkspace,
            fetchWorkspaceOptions,
            workspaceOptions,
            workspaceSelected,
            setWorkspace,
            sidebarOpen,
            inputMessage,
            selectedModeIds,
            pendingGoalMode,
            chatSessions,
            activeSessionId,
            activeSessionRunning,
            messages,
            visibleMessages,
            hiddenCount,
            isTyping,
            submitInFlight,
            submissionNotice,
            status,
            tokenUsage,
            tokenUsageLabel,
            tokenContextPercent,
            formatTokenCount,
            canIntervene,
            activeModal,
            openModal,
            openOrchestrationConsole,
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
            reloadAgent,
            sendMessage,
            switchChatSession,
            createChatSession,
            closeChatSession,
            attachedImages,
            attachmentError,
            attachmentUploading,
            fileInputRef,
            triggerImagePicker,
            handleImagePicker,
            handleInputPaste,
            handleInputDrop,
            removeAttachedImage,
            modeCommands,
            selectedModeCommands,
            applyModeCommand,
            confirmGoalMode,
            cancelGoalMode,
            renderMarkdown,
            historySessionView,
            selectedHistorySessionId,
            selectedHistorySession,
            historyMessageView,
            historySearchQuery,
            historySearchActive,
            historySearchResultView,
            historySearchLoading,
            historySearchError,
            historyTitleDraft,
            historyNotice,
            historyLoading,
            historySavingTitle,
            historyError,
            refreshHistoryData,
            selectHistorySession,
            restoreHistorySession,
            renameHistorySession,
            exportHistorySession,
            memoryFilesView,
            selectedMemoryFile,
            memoryContent,
            memoryRoot,
            memoryLoading,
            memoryError,
            memoryFileIsMarkdown,
            fetchMemoryList,
            selectMemoryFile,
            refreshMemoryList,
            backupRoot,
            backupItems,
            backupLoading,
            backupCreating,
            backupNotice,
            backupError,
            goalState,
            goalObjective,
            goalBudgetMinutes,
            goalMaxTurns,
            goalDonePrompt,
            goalLoading,
            goalNotice,
            goalError,
            formatGoalMinutes,
            fetchGoalStatus,
            startGoalMode,
            stopGoalMode,
            hiveState,
            hiveObjective,
            hiveBudgetMinutes,
            hiveMaxTurns,
            hiveWorkerCount,
            hiveLoading,
            hiveNotice,
            hiveError,
            fetchHiveStatus,
            startHiveMode,
            stopHiveMode,
            orchestrationTab,
            switchOrchestrationTab,
            hivePosts,
            hivePostsLoading,
            hivePostsError,
            hiveBbsOffline,
            hiveBbsUrl,
            hivePostAuthor,
            hivePostContent,
            hivePosting,
            hiveAutoRefresh,
            hivePostFilter,
            hivePostSearch,
            hiveControlTarget,
            hiveExtendMinutes,
            hiveExtendTurns,
            hiveBbsComposerOpen,
            hiveExpandedPosts,
            hiveFilteredPosts,
            fetchHivePosts,
            refreshHivePanel,
            postHiveMessage,
            appendHiveMention,
            hiveControlAgent,
            extendHiveBudget,
            hiveStatusLabel,
            hiveStatusDotClass,
            hivePostRoleLabel,
            hivePostRoleClass,
            formatHivePostTime,
            formatHiveDuration,
            hivePostPreview,
            hivePostExpanded,
            toggleHivePostExpanded,
            communicationTools,
            communicationPath,
            selectedCommunicationId,
            selectedCommunicationTool,
            communicationLoading,
            communicationSaving,
            communicationBusyId,
            communicationNotice,
            communicationError,
            interventionOpen,
            interventionText,
            interventionNotice,
            interventionError,
            interventionSaving,
            openIntervention,
            closeIntervention,
            submitIntervention,
            fetchCommunicationConfigs,
            selectCommunicationTool,
            communicationDraft,
            communicationStatusClass,
            communicationStatusText,
            saveCommunicationConfig,
            runCommunicationAction,
            fetchBackups,
            createBackup,
            formatBackupSize,
            petConfig,
            petConfigPath,
            petSkins,
            petLoading,
            petSaving,
            petNotice,
            petError,
            fetchPetConfig,
            fetchPetSkins,
            savePetConfig,
            selectPetSkin,
            deletePetSkin,
            resetPetConfig,
            copyToClipboard,
            switchLLM,
            stopTask,
            newConversation,
            toggleAutonomous,
            triggerAutonomous,
             injectSysPrompt,
             formatTime,
            updateThreshold,
            onChatScroll,
            loadMoreHistory,
            jumpToLatest,
            handleCompositionStart,
            handleCompositionEnd,
            handleInputKeydown,
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
