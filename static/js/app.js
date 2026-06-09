document.addEventListener('DOMContentLoaded', () => {
    // === 导航与视图切换 ===
    const navItems = document.querySelectorAll('.nav-item');
    const viewSections = document.querySelectorAll('.view-section');
    const escapeHtmlGlobal = (value) => String(value || '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');

    function showView(targetView, activateNav = true) {
        if (activateNav) {
            navItems.forEach(nav => {
                nav.classList.toggle('active', nav.getAttribute('data-view') === targetView);
            });
        }

        viewSections.forEach(section => {
            section.classList.toggle('hidden', section.id !== `view-${targetView}`);
        });

        if (targetView === 'stats') loadStats();
        if (targetView === 'library') loadLibrary();
    }

    navItems.forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            showView(item.getAttribute('data-view'));
        });
    });

    // === 搜索功能 ===
    const searchInput = document.getElementById('searchInput');
    const searchBtn = document.getElementById('searchBtn');
    const searchResults = document.getElementById('searchResults');
    const searchLoading = document.getElementById('searchLoading');

    async function performSearch() {
        const query = searchInput.value.trim();
        if (!query) return;

        const searchType = document.querySelector('input[name="searchType"]:checked').value;
        
        searchResults.innerHTML = '';
        searchLoading.classList.remove('hidden');

        try {
            const res = await fetch(`/api/search?q=${encodeURIComponent(query)}&search_type=${searchType}&top_k=20`);
            const data = await res.json();
            
            searchLoading.classList.add('hidden');
            renderPapers(data.results || [], searchResults);
        } catch (error) {
            console.error('Search failed:', error);
            searchLoading.classList.add('hidden');
            searchResults.innerHTML = `<div class="empty-state"><p style="color: #ef4444;">搜索请求失败: ${error.message}</p></div>`;
        }
    }

    searchBtn.addEventListener('click', performSearch);
    searchInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') performSearch();
    });

    // === 渲染论文列表 ===
    function renderPapers(papers, container) {
        if (!papers || papers.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <i class="fa-solid fa-ghost"></i>
                    <p>No matching papers found in memory.</p>
                </div>`;
            return;
        }

        container.innerHTML = papers.map(paper => {
            const hasPdf = Boolean(paper.file_path || paper.source === 'local_pdf' || paper.parse_status === 'full_text');
            return `
            <div class="paper-card" data-id="${escapeHtmlGlobal(paper.id)}">
                <h3 class="paper-title" onclick="openPaperDetail('${escapeHtmlGlobal(paper.id)}')">${escapeHtmlGlobal(paper.title)}</h3>
                <div class="paper-meta">
                    ${paper.authors ? `<span><i class="fa-solid fa-users"></i> ${escapeHtmlGlobal(paper.authors)}</span>` : ''}
                    <span><i class="fa-regular fa-calendar"></i> ${escapeHtmlGlobal(paper.publish_date || 'Unknown')}</span>
                    ${paper.journal ? `<span><i class="fa-solid fa-book"></i> ${escapeHtmlGlobal(paper.journal)}</span>` : ''}
                    <span style="color: var(--accent-primary)">
                        <i class="fa-solid fa-bolt"></i> ${escapeHtmlGlobal(paper.search_type || 'db')}
                    </span>
                </div>
                <div class="paper-abstract">${escapeHtmlGlobal(paper.abstract || 'No abstract available.')}</div>
                <div class="paper-actions">
                    <div class="tag-list">
                        <span class="tag">${escapeHtmlGlobal(paper.source || 'local')}</span>
                        ${paper.language ? `<span class="tag">${escapeHtmlGlobal(paper.language)}</span>` : ''}
                    </div>
                    <div>
                        ${hasPdf ? `
                        <button class="icon-btn" onclick="openPdfReader('${escapeHtmlGlobal(paper.id)}')" title="?? PDF">
                            <i class="fa-solid fa-book-open-reader"></i>
                        </button>` : ''}
                        <button class="icon-btn ${paper.is_favorited ? 'active' : ''}" onclick="toggleFavorite('${escapeHtmlGlobal(paper.id)}', this)" title="??">
                            <i class="fa-solid fa-star"></i>
                        </button>
                        ${paper.url ? `
                        <a href="${escapeHtmlGlobal(paper.url)}" target="_blank" class="icon-btn" title="Open source" onclick="event.stopPropagation()">
                            <i class="fa-solid fa-external-link-alt"></i>
                        </a>` : ''}
                    </div>
                </div>
            </div>`;
        }).join('');
    }

    // === PDF Reader ===
    const readerState = {
        paperId: null,
        paper: null,
        pdfDoc: null,
        pageNum: 1,
        scale: 1.2,
        rendering: false,
        pendingPage: null,
        returnView: 'search'
    };

    const readerTitle = document.getElementById('readerTitle');
    const readerStatus = document.getElementById('readerStatus');
    const readerPageInput = document.getElementById('readerPageInput');
    const readerPageCount = document.getElementById('readerPageCount');
    const readerChunks = document.getElementById('readerChunks');
    const pdfCanvas = document.getElementById('pdfCanvas');

    if (window.pdfjsLib) {
        pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';
    }

    function updateReaderControls() {
        const total = readerState.pdfDoc ? readerState.pdfDoc.numPages : 0;
        readerPageInput.value = readerState.pageNum;
        readerPageInput.max = total || 1;
        readerPageCount.textContent = `/ ${total}`;
        document.getElementById('readerPrevBtn').disabled = !total || readerState.pageNum <= 1;
        document.getElementById('readerNextBtn').disabled = !total || readerState.pageNum >= total;
        readerStatus.textContent = total ? `Page ${readerState.pageNum} of ${total}` : 'No paper loaded';
    }

    async function renderPdfPage(pageNum) {
        if (!readerState.pdfDoc || readerState.rendering) {
            readerState.pendingPage = pageNum;
            return;
        }
        readerState.rendering = true;
        const page = await readerState.pdfDoc.getPage(pageNum);
        const viewport = page.getViewport({ scale: readerState.scale });
        const context = pdfCanvas.getContext('2d');
        pdfCanvas.width = viewport.width;
        pdfCanvas.height = viewport.height;
        await page.render({ canvasContext: context, viewport }).promise;
        readerState.rendering = false;
        updateReaderControls();
        if (readerState.pendingPage && readerState.pendingPage !== pageNum) {
            const pending = readerState.pendingPage;
            readerState.pendingPage = null;
            await queuePdfPage(pending);
        } else {
            readerState.pendingPage = null;
        }
    }

    async function queuePdfPage(pageNum) {
        if (!readerState.pdfDoc) return;
        const total = readerState.pdfDoc.numPages;
        readerState.pageNum = Math.min(Math.max(Number(pageNum) || 1, 1), total);
        updateReaderControls();
        await renderPdfPage(readerState.pageNum);
    }

    async function loadReaderChunks(paperId) {
        readerChunks.innerHTML = '<p class="reader-empty">Loading chunks...</p>';
        try {
            const res = await fetch(`/api/papers/${paperId}/chunks?limit=200`);
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Failed to load chunks');
            const chunks = data.chunks || [];
            if (!chunks.length) {
                readerChunks.innerHTML = '<p class="reader-empty">No chunks available for this paper.</p>';
                return;
            }
            readerChunks.innerHTML = chunks.map(chunk => `
                <button class="reader-chunk" data-page="${chunk.page_start || 1}">
                    <span>Chunk ${chunk.chunk_index + 1}${chunk.page_start ? ` ? p.${chunk.page_start}${chunk.page_end && chunk.page_end !== chunk.page_start ? `-${chunk.page_end}` : ''}` : ''}</span>
                    <p>${escapeHtmlGlobal((chunk.content || '').slice(0, 220))}</p>
                </button>
            `).join('');
            readerChunks.querySelectorAll('.reader-chunk').forEach(btn => {
                btn.addEventListener('click', () => queuePdfPage(Number(btn.dataset.page || 1)));
            });
        } catch (error) {
            readerChunks.innerHTML = `<p class="reader-empty">${escapeHtmlGlobal(error.message)}</p>`;
        }
    }

    window.openPdfReader = async (paperId) => {
        if (window.event) window.event.stopPropagation();
        if (!window.pdfjsLib) {
            alert('PDF.js failed to load. Check your network connection.');
            return;
        }
        readerState.returnView = document.querySelector('.view-section:not(.hidden)')?.id?.replace('view-', '') || 'search';
        showView('reader', false);
        readerTitle.textContent = 'Loading PDF...';
        readerStatus.textContent = 'Preparing reader';
        readerChunks.innerHTML = '<p class="reader-empty">Loading chunks...</p>';
        const context = pdfCanvas.getContext('2d');
        context.clearRect(0, 0, pdfCanvas.width, pdfCanvas.height);

        try {
            const paperRes = await fetch(`/api/papers/${paperId}`);
            const paper = await paperRes.json();
            if (!paperRes.ok) throw new Error(paper.detail || 'Paper not found');
            readerState.paperId = paperId;
            readerState.paper = paper;
            readerState.pageNum = 1;
            readerState.scale = 1.2;
            readerTitle.textContent = paper.title || 'PDF Reader';

            const pdfUrl = `/api/papers/${paperId}/pdf`;
            readerState.pdfDoc = await pdfjsLib.getDocument(pdfUrl).promise;
            updateReaderControls();
            await renderPdfPage(1);
            await loadReaderChunks(paperId);
        } catch (error) {
            readerTitle.textContent = 'PDF Reader';
            readerStatus.textContent = 'Failed to load PDF';
            readerChunks.innerHTML = `<p class="reader-empty">${escapeHtmlGlobal(error.message)}</p>`;
        }
    };

    document.getElementById('readerBackBtn').addEventListener('click', () => {
        showView(readerState.returnView || 'search');
    });
    document.getElementById('readerPrevBtn').addEventListener('click', () => queuePdfPage(readerState.pageNum - 1));
    document.getElementById('readerNextBtn').addEventListener('click', () => queuePdfPage(readerState.pageNum + 1));
    document.getElementById('readerZoomOutBtn').addEventListener('click', () => {
        readerState.scale = Math.max(0.6, readerState.scale - 0.2);
        queuePdfPage(readerState.pageNum);
    });
    document.getElementById('readerZoomInBtn').addEventListener('click', () => {
        readerState.scale = Math.min(2.4, readerState.scale + 0.2);
        queuePdfPage(readerState.pageNum);
    });
    readerPageInput.addEventListener('change', () => queuePdfPage(Number(readerPageInput.value)));

    // === 弹窗详情 ===
    const modal = document.getElementById('paperModal');
    const modalBody = document.getElementById('modalBody');
    const closeBtn = document.querySelector('.close-btn');

    window.openPaperDetail = async (id) => {
        modal.style.display = 'block';
        modalBody.innerHTML = '<div class="loading-spinner"><div class="spinner"></div></div>';
        
        try {
            const res = await fetch(`/api/papers/${id}`);
            const paper = await res.json();
            
            modalBody.innerHTML = `
                <h2 class="detail-title">${paper.title}</h2>
                <div class="detail-authors">${paper.authors || 'Unknown Authors'}</div>
                
                <div class="paper-meta" style="margin-bottom: 30px; border-bottom: 1px solid var(--border-color); padding-bottom: 20px;">
                    <span><i class="fa-regular fa-calendar"></i> ${paper.publish_date || 'Unknown'}</span>
                    <span><i class="fa-solid fa-book"></i> ${paper.journal || paper.source}</span>
                    <span><i class="fa-solid fa-quote-right"></i> 被引: ${paper.citation_count || 0}</span>
                    ${paper.doi ? `<span>DOI: ${paper.doi}</span>` : ''}
                </div>

                <div class="detail-section">
                    <h4>摘要 Abstract</h4>
                    <div class="detail-abstract">${paper.abstract || 'No abstract available.'}</div>
                </div>

                ${paper.keywords ? `
                <div class="detail-section">
                    <h4>关键词 Keywords</h4>
                    <div class="tag-list" style="flex-wrap: wrap;">
                        ${paper.keywords.split(',').map(k => `<span class="tag">${k.trim()}</span>`).join('')}
                    </div>
                </div>` : ''}

                <div style="margin-top: 30px;">
                    ${paper.file_path ? `<button class="primary-btn" onclick="modal.style.display='none'; openPdfReader('${paper.id}')"><i class="fa-solid fa-book-open-reader"></i> 阅读 PDF</button>` : ''}
                    ${paper.url ? `<a href="${paper.url}" target="_blank" class="primary-btn"><i class="fa-solid fa-file-pdf"></i> 获取原文</a>` : ''}
                </div>
            `;
        } catch (error) {
            modalBody.innerHTML = `<p style="color: #ef4444;">加载失败: ${error.message}</p>`;
        }
    };

    closeBtn.onclick = () => modal.style.display = 'none';
    window.onclick = (event) => {
        if (event.target == modal) modal.style.display = 'none';
    };

    // === 交互功能 ===
    window.toggleFavorite = async (id, btn) => {
        event.stopPropagation();
        try {
            const res = await fetch(`/api/papers/${id}/favorite`, { method: 'POST' });
            const data = await res.json();
            if (data.success) {
                if (data.is_favorited) {
                    btn.classList.add('active');
                } else {
                    btn.classList.remove('active');
                }
            }
        } catch (error) {
            console.error('Toggle favorite failed:', error);
        }
    };

    // === 爬虫触发 ===
    document.getElementById('triggerCrawlBtn').addEventListener('click', async () => {
        const source = document.getElementById('crawlSource').value;
        const topic = document.getElementById('crawlTopic').value.trim();
        const btn = document.getElementById('triggerCrawlBtn');
        const logsDiv = document.getElementById('crawlLogs');
        
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> 正在派遣 Agent...';
        
        try {
            const res = await fetch('/api/crawl/trigger', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ source, topic, max_results: 20 })
            });
            const data = await res.json();
            
            logsDiv.innerHTML = `
                <div style="padding: 16px; background: rgba(16, 185, 129, 0.1); border-left: 4px solid #10b981; border-radius: 4px; margin-top: 20px;">
                    <p style="color: #10b981;"><i class="fa-solid fa-check-circle"></i> ${data.message}</p>
                    <p style="font-size: 13px; color: var(--text-secondary); margin-top: 8px;">任务已在后台执行，请稍后在搜索或数据概览中查看结果。</p>
                </div>
            ` + logsDiv.innerHTML;
        } catch (error) {
            alert('触发失败: ' + error.message);
        } finally {
            btn.disabled = false;
            btn.innerHTML = '<i class="fa-solid fa-rocket"></i> 派出 Agent';
        }
    });

    // === 统计视图加载 ===
    document.getElementById('uploadPdfBtn').addEventListener('click', async () => {
        const fileInput = document.getElementById('pdfFile');
        const btn = document.getElementById('uploadPdfBtn');
        const logsDiv = document.getElementById('crawlLogs');
        const file = fileInput.files[0];

        if (!file) {
            alert('请选择 PDF 文件');
            return;
        }

        const formData = new FormData();
        formData.append('file', file);
        formData.append('title', document.getElementById('pdfTitle').value.trim());
        formData.append('authors', document.getElementById('pdfAuthors').value.trim());
        formData.append('keywords', document.getElementById('pdfKeywords').value.trim());

        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> 正在解析...';

        try {
            const res = await fetch('/api/papers/upload-pdf', {
                method: 'POST',
                body: formData
            });
            const data = await res.json();
            if (!res.ok) {
                throw new Error(data.detail || '上传失败');
            }

            logsDiv.innerHTML = `
                <div style="padding: 16px; background: rgba(16, 185, 129, 0.1); border-left: 4px solid #10b981; border-radius: 4px; margin-top: 20px;">
                    <p style="color: #10b981;"><i class="fa-solid fa-check-circle"></i> PDF 已导入：${data.title}</p>
                    <p style="font-size: 13px; color: var(--text-secondary); margin-top: 8px;">页数：${data.pages}，全文块：${data.chunks}，状态：${data.parse_status}</p>
                </div>
            ` + logsDiv.innerHTML;

            fileInput.value = '';
            document.getElementById('pdfTitle').value = '';
            document.getElementById('pdfAuthors').value = '';
            document.getElementById('pdfKeywords').value = '';
        } catch (error) {
            alert('PDF 导入失败: ' + error.message);
        } finally {
            btn.disabled = false;
            btn.innerHTML = '<i class="fa-solid fa-file-arrow-up"></i> 导入 PDF';
        }
    });

    async function loadStats() {
        const grid = document.getElementById('statsGrid');
        grid.innerHTML = '<div class="loading-spinner"><div class="spinner"></div></div>';
        
        try {
            const res = await fetch('/api/stats');
            const stats = await res.json();
            const usage = stats.agent_usage || {};
            const formatNumber = (value) => Number(value || 0).toLocaleString();
            const escapeHtml = (value) => String(value || '')
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#039;');
            const recentRows = (usage.recent || []).map(item => `
                <tr>
                    <td>${escapeHtml(item.created_at || '-')}</td>
                    <td>${escapeHtml(item.model || '-')}</td>
                    <td>${formatNumber(item.input_tokens)}</td>
                    <td>${formatNumber(item.output_tokens)}</td>
                    <td>${formatNumber(item.total_tokens)}</td>
                    <td>${formatNumber(item.tool_calls)}</td>
                </tr>
            `).join('');
            const ragPanels = (stats.recent_rag_hits || []).map(call => {
                const hits = (call.hits || []).slice(0, 5).map(hit => `
                    <div class="rag-hit-item">
                        <div class="rag-hit-title">${escapeHtml(hit.title || '未命名论文')}</div>
                        <div class="rag-hit-meta">
                            ${escapeHtml(hit.search_type || '-')} · score ${Number(hit.search_score || 0).toFixed(4)}
                            ${hit.page_start ? ` · p.${hit.page_start}${hit.page_end && hit.page_end !== hit.page_start ? `-${hit.page_end}` : ''}` : ''}
                        </div>
                        <p>${escapeHtml(hit.snippet || '')}</p>
                    </div>
                `).join('');
                return `
                    <div class="rag-call-card">
                        <div class="rag-call-header">
                            <strong>${escapeHtml(call.session_title || '未命名会话')}</strong>
                            <span>${escapeHtml(call.created_at || '-')}</span>
                        </div>
                        ${hits || '<p class="rag-empty">这次检索没有返回全文片段</p>'}
                    </div>
                `;
            }).join('');
            
            grid.innerHTML = `
                <div class="stat-card">
                    <div class="stat-value">${formatNumber(stats.total_papers)}</div>
                    <div class="stat-label">文献总数</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value" style="color: #eab308;">${formatNumber(stats.favorited_papers)}</div>
                    <div class="stat-label">已收藏</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value" style="color: var(--accent-secondary);">${formatNumber(stats.total_crawls)}</div>
                    <div class="stat-label">爬虫执行次数</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value" style="color: #10b981;">${formatNumber(stats.total_searches)}</div>
                    <div class="stat-label">智能检索次数</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value" style="color: #38bdf8;">${formatNumber(usage.total_calls)}</div>
                    <div class="stat-label">Agent 调用次数</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value" style="color: #f97316;">${formatNumber(usage.total_tokens)}</div>
                    <div class="stat-label">累计 Token</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">${formatNumber(usage.input_tokens)}</div>
                    <div class="stat-label">输入 Token</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">${formatNumber(usage.output_tokens)}</div>
                    <div class="stat-label">输出 Token</div>
                </div>
                <div class="usage-panel">
                    <div class="usage-panel-header">
                        <h3>最近 Agent 调用</h3>
                        <span>工具调用 ${formatNumber(usage.tool_calls)} 次</span>
                    </div>
                    <div class="usage-table-wrap">
                        <table class="usage-table">
                            <thead>
                                <tr>
                                    <th>时间</th>
                                    <th>模型</th>
                                    <th>输入</th>
                                    <th>输出</th>
                                    <th>总计</th>
                                    <th>工具</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${recentRows || '<tr><td colspan="6">暂无 Agent 调用记录</td></tr>'}
                            </tbody>
                        </table>
                    </div>
                </div>
                <div class="usage-panel rag-debug-panel">
                    <div class="usage-panel-header">
                        <h3>最近 RAG 命中</h3>
                        <span>search_chunks 调试记录</span>
                    </div>
                    <div class="rag-hit-list">
                        ${ragPanels || '<p class="rag-empty">暂无 RAG 检索记录。先在 AI 对话里问一个需要查论文全文的问题。</p>'}
                    </div>
                </div>
            `;
        } catch (error) {
            grid.innerHTML = `<p style="color: #ef4444;">加载失败: ${error.message}</p>`;
        }
    }

    // === 我的收藏加载 ===
    async function loadLibrary() {
        // 复用搜索结果容器，但在一个新的 section 中渲染
        // 为简化示例，这里就不额外展开，实际可以通过调用 /api/papers?favorited=true 实现
    }

    // === AI 对话逻辑 ===
    let currentChatMessages = [];
    let currentChatSessionId = localStorage.getItem('paperAgentChatSessionId') || null;
    const chatInput = document.getElementById('chatInput');
    const chatSendBtn = document.getElementById('chatSendBtn');
    const chatHistory = document.getElementById('chatHistory');
    const chatPanel = document.getElementById('view-chat');
    const chatToggleBtn = document.getElementById('chatToggleBtn');
    const chatCloseBtn = document.getElementById('chatCloseBtn');

    function openChatPanel() {
        chatPanel.classList.remove('hidden');
        chatToggleBtn.classList.add('hidden');
        loadChatSession();
        scrollToBottom();
        chatInput.focus();
    }

    function closeChatPanel() {
        chatPanel.classList.add('hidden');
        chatToggleBtn.classList.remove('hidden');
    }

    chatToggleBtn.addEventListener('click', openChatPanel);
    chatCloseBtn.addEventListener('click', closeChatPanel);

    // 简单 Markdown 解析器 (加粗和换行)
    function parseSimpleMarkdown(text) {
        if (!text) return '';
        let html = text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
        html = html.replace(/\n/g, '<br>');
        return html;
    }

    // 滚动到底部
    function scrollToBottom() {
        chatHistory.scrollTop = chatHistory.scrollHeight;
    }

    // 渲染聊天记录
    function renderChatMessages() {
        // 清空除了初始欢迎语之外的全部气泡
        const initialWelcome = chatHistory.firstElementChild;
        chatHistory.innerHTML = '';
        if (initialWelcome) chatHistory.appendChild(initialWelcome);

        currentChatMessages.forEach(msg => {
            if (msg.role === 'system') return; // 不渲染 system prompt

            const bubble = document.createElement('div');
            bubble.classList.add('chat-bubble');

            if (msg.role === 'user') {
                bubble.classList.add('user-bubble');
                bubble.innerHTML = `<div class="bubble-content">${parseSimpleMarkdown(msg.content)}</div>`;
            } else if (msg.role === 'assistant') {
                if (msg.tool_calls && msg.tool_calls.length > 0) {
                    // 模型尝试调用工具的提示气泡
                    bubble.classList.add('tool-bubble');
                    const toolNames = msg.tool_calls.map(tc => tc.function.name).join(', ');
                    bubble.innerHTML = `
                        <div class="tool-content">
                            <i class="fa-solid fa-wrench"></i>
                            <span>Agent 正在调用内部工具: ${toolNames}...</span>
                        </div>
                    `;
                } else if (msg.content) {
                    // 正常的助手回复
                    bubble.classList.add('assistant-bubble');
                    bubble.innerHTML = `<div class="bubble-content">${parseSimpleMarkdown(msg.content)}</div>`;
                } else {
                    return; // 防止空状态
                }
            } else if (msg.role === 'tool') {
                bubble.classList.add('tool-bubble');
                bubble.innerHTML = `
                    <div class="tool-content" style="border-color: #10b981;">
                        <i class="fa-solid fa-check" style="color: #10b981;"></i>
                        <span>工具 [${msg.name}] 执行完毕</span>
                    </div>
                `;
            }
            chatHistory.appendChild(bubble);
        });
        scrollToBottom();
    }

    // 发送消息
    async function loadChatSession() {
        if (!currentChatSessionId || currentChatMessages.length > 0) return;
        try {
            const res = await fetch(`/api/agent/chat/${currentChatSessionId}`);
            if (!res.ok) {
                localStorage.removeItem('paperAgentChatSessionId');
                currentChatSessionId = null;
                return;
            }
            const data = await res.json();
            currentChatMessages = data.messages || [];
            renderChatMessages();
        } catch (error) {
            console.warn('Load chat session failed:', error);
        }
    }

    async function sendChatMessage() {
        const text = chatInput.value.trim();
        if (!text) return;

        // 构建本地消息追加
        currentChatMessages.push({ role: 'user', content: text });
        chatInput.value = '';
        chatInput.style.height = 'auto'; // reset height
        
        renderChatMessages();

        // 禁用输入并显示 Loading 气泡
        chatInput.disabled = true;
        chatSendBtn.disabled = true;

        const loadingBubble = document.createElement('div');
        loadingBubble.classList.add('chat-bubble', 'assistant-bubble');
        loadingBubble.id = 'chatLoadingBubble';
        loadingBubble.innerHTML = `
            <div class="bubble-content" style="padding: 10px 18px;">
                <div class="typing-indicator">
                    <span></span><span></span><span></span>
                </div>
            </div>
        `;
        chatHistory.appendChild(loadingBubble);
        scrollToBottom();

        try {
            const res = await fetch('/api/agent/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    session_id: currentChatSessionId,
                    message: text
                })
            });
            const data = await res.json();
            if (!res.ok) {
                throw new Error(data.detail || '请求失败');
            }
            
            // 用后端返回的带有上下文和工具调用结果的 messages 覆盖当前数组
            if (data.session_id) {
                currentChatSessionId = data.session_id;
                localStorage.setItem('paperAgentChatSessionId', currentChatSessionId);
            }
            if (data.messages) {
                currentChatMessages = data.messages;
            }
        } catch (error) {
            console.error('Chat error:', error);
            currentChatMessages.push({ role: 'assistant', content: `❌ 请求失败: ${error.message}` });
        } finally {
            chatInput.disabled = false;
            chatSendBtn.disabled = false;
            chatInput.focus();
            renderChatMessages(); // 重新渲染最终状态（移除 loading 气泡）
        }
    }

    chatSendBtn.addEventListener('click', sendChatMessage);
    
    chatInput.addEventListener('keypress', (e) => {
        // 回车发送，Shift+回车换行
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendChatMessage();
        }
    });

    // 自动调整文本框高度
    chatInput.addEventListener('input', function() {
        this.style.height = 'auto';
        this.style.height = (this.scrollHeight) + 'px';
    });

});
