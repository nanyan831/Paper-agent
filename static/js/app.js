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
    const recentPdfs = document.getElementById('recentPdfs');
    const refreshRecentPdfsBtn = document.getElementById('refreshRecentPdfsBtn');
    const evidenceInput = document.getElementById('evidenceInput');
    const evidenceLookupBtn = document.getElementById('evidenceLookupBtn');
    const evidenceResults = document.getElementById('evidenceResults');

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
                        <button class="icon-btn" onclick="openPdfReader('${escapeHtmlGlobal(paper.id)}')" title="Read PDF">
                            <i class="fa-solid fa-book-open-reader"></i>
                        </button>` : ''}
                        <button class="icon-btn ${paper.is_favorited ? 'active' : ''}" onclick="toggleFavorite('${escapeHtmlGlobal(paper.id)}', this)" title="Favorite">
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
        renderError: null,
        pendingPage: null,
        chunks: [],
        pageTextCache: {},
        lastTranslateSource: '',
        returnView: 'search'
    };

    const readerTitle = document.getElementById('readerTitle');
    const readerStatus = document.getElementById('readerStatus');
    const readerPageInput = document.getElementById('readerPageInput');
    const readerPageCount = document.getElementById('readerPageCount');
    const readerChunks = document.getElementById('readerChunks');
    const pdfCanvas = document.getElementById('pdfCanvas');
    const readerEvidenceInput = document.getElementById('readerEvidenceInput');
    const readerEvidenceBtn = document.getElementById('readerEvidenceBtn');
    const readerEvidenceResults = document.getElementById('readerEvidenceResults');
    const readerTranslateSource = document.getElementById('readerTranslateSource');
    const readerTranslateResult = document.getElementById('readerTranslateResult');
    const readerTranslateBtn = document.getElementById('readerTranslateBtn');
    const readerRetryTranslateBtn = document.getElementById('readerRetryTranslateBtn');
    const readerTranslateStatus = document.getElementById('readerTranslateStatus');
    const readerUsePageTextBtn = document.getElementById('readerUsePageTextBtn');
    const readerPrevBtn = document.getElementById('readerPrevBtn');
    const readerNextBtn = document.getElementById('readerNextBtn');
    const readerZoomOutBtn = document.getElementById('readerZoomOutBtn');
    const readerZoomInBtn = document.getElementById('readerZoomInBtn');

    if (window.pdfjsLib) {
        pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';
    }

    function updateReaderControls() {
        const total = readerState.pdfDoc ? readerState.pdfDoc.numPages : 0;
        readerPageInput.value = readerState.pageNum;
        readerPageInput.max = total || 1;
        readerPageInput.disabled = !total;
        readerPageCount.textContent = `/ ${total}`;
        readerPrevBtn.disabled = !total || readerState.pageNum <= 1;
        readerNextBtn.disabled = !total || readerState.pageNum >= total;
        readerZoomOutBtn.disabled = !total || readerState.scale <= 0.6;
        readerZoomInBtn.disabled = !total || readerState.scale >= 2.4;
        if (readerState.renderError) {
            readerStatus.textContent = readerState.renderError;
        } else if (total) {
            readerStatus.textContent = readerState.rendering
                ? `Rendering page ${readerState.pageNum} of ${total}`
                : `Page ${readerState.pageNum} of ${total} - ${Math.round(readerState.scale * 100)}%`;
        } else {
            readerStatus.textContent = 'No paper loaded';
        }
        highlightReaderChunks();
    }

    function renderRecentPdfs(papers) {
        if (!recentPdfs) return;
        const pdfPapers = (papers || []).filter(paper => paper.file_path || paper.source === 'local_pdf');
        if (!pdfPapers.length) {
            recentPdfs.innerHTML = `
                <div class="recent-placeholder">
                    <i class="fa-regular fa-file-pdf"></i>
                    <span>还没有收录 PDF，先导入资料后再找出处。</span>
                </div>`;
            return;
        }

        recentPdfs.innerHTML = pdfPapers.map(paper => {
            const chunkCount = Number(paper.chunk_count || 0);
            const pageCount = Number(paper.page_count || 0);
            const needsOcrHint = pageCount === 0 || chunkCount === 0;
            return `
                <article class="recent-pdf-card${needsOcrHint ? ' has-quality-warning' : ''}">
                    <div class="recent-pdf-main">
                        <h4 title="${escapeHtmlGlobal(paper.title)}">${escapeHtmlGlobal(paper.title || '未命名资料')}</h4>
                        <p>${escapeHtmlGlobal(paper.authors || '未知作者')}</p>
                        <div class="recent-pdf-meta">
                            ${pageCount ? `<span><i class="fa-regular fa-file-lines"></i> ${pageCount} 页</span>` : ''}
                            <span><i class="fa-solid fa-layer-group"></i> ${chunkCount} 个片段</span>
                            <span><i class="fa-solid fa-circle-check"></i> ${escapeHtmlGlobal(paper.parse_status || 'unknown')}</span>
                        </div>
                        ${needsOcrHint ? '<div class="quality-warning"><i class="fa-solid fa-triangle-exclamation"></i> 可能是扫描版/不可检索，需要 OCR 或换 PDF</div>' : ''}
                    </div>
                    <button class="reader-open-btn" onclick="openPdfReader('${escapeHtmlGlobal(paper.id)}')" title="打开原文">
                        <i class="fa-solid fa-book-open-reader"></i>
                    </button>
                </article>`;
        }).join('');
    }

    async function loadRecentPdfs() {
        if (!recentPdfs) return;
        recentPdfs.innerHTML = '<div class="recent-placeholder">正在加载最近收录资料...</div>';
        try {
            const res = await fetch('/api/papers?source=local_pdf&limit=6');
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || '加载最近收录失败');
            renderRecentPdfs(data.papers || []);
        } catch (error) {
            recentPdfs.innerHTML = `<div class="recent-placeholder error">${escapeHtmlGlobal(error.message)}</div>`;
        }
    }

    if (refreshRecentPdfsBtn) {
        refreshRecentPdfsBtn.addEventListener('click', loadRecentPdfs);
    }

    function parseSourcePage(value, fallback = 1) {
        const parsed = parseInt(value, 10);
        return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
    }

    function truncateSourceText(value, maxChars = 260) {
        const text = String(value || '').replace(/\s+/g, ' ').trim();
        if (text.length <= maxChars) return text;
        return `${text.slice(0, maxChars).trim()}...`;
    }

    function normalizeSourceItem(source) {
        const item = source || {};
        const pageStart = parseSourcePage(item.page_start ?? item.page ?? item.pageStart ?? item.page_end, 1);
        const pageEnd = Math.max(parseSourcePage(item.page_end, pageStart), pageStart);
        const paperId = String(item.paper_id || item.paperId || '').trim();
        const snippet = truncateSourceText(item.snippet || item.content || '', 260);
        return {
            paperId,
            canJump: Boolean(paperId),
            title: item.title || item.paper_title || item.source_title || '未命名资料',
            pageStart,
            pageEnd,
            pageLabel: pageEnd !== pageStart ? `p.${pageStart}-${pageEnd}` : `p.${pageStart}`,
            pageLabelZh: pageEnd !== pageStart ? `第 ${pageStart}-${pageEnd} 页` : `第 ${pageStart} 页`,
            snippet,
            authors: item.authors || '',
            source: item.source || 'local_pdf',
            searchType: item.search_type || ''
        };
    }

    function renderEvidenceResults(chunks) {
        if (!evidenceResults) return;
        const candidates = (chunks || []).slice(0, 5).map(normalizeSourceItem);
        evidenceResults.classList.remove('hidden');
        if (!candidates.length) {
            evidenceResults.innerHTML = `
                <div class="evidence-empty">
                    <i class="fa-regular fa-circle-question"></i>
                    <span>本地资料库暂时没有找到可用出处，建议先导入相关 PDF。</span>
                </div>`;
            return;
        }

        evidenceResults.innerHTML = `
            <div class="evidence-result-title">可能来源</div>
            ${candidates.map((source, index) => `
                <article class="evidence-card${source.canJump ? ' has-jump' : ''}">
                    <div class="evidence-rank">${index + 1}</div>
                    <div class="evidence-body">
                        <h4 class="${source.canJump ? 'jumpable' : 'disabled'}" ${source.canJump ? `onclick="openPdfSource('${escapeHtmlGlobal(source.paperId)}', ${source.pageStart})"` : ''}>${escapeHtmlGlobal(source.title)}</h4>
                        <p>${escapeHtmlGlobal(source.snippet || '暂无原文片段，可打开原文继续核对。')}</p>
                        <div class="evidence-meta">
                            ${source.authors ? `<span><i class="fa-solid fa-users"></i> ${escapeHtmlGlobal(source.authors)}</span>` : ''}
                            <span><i class="fa-solid fa-file-lines"></i> ${escapeHtmlGlobal(source.pageLabelZh)}</span>
                            <span><i class="fa-solid fa-database"></i> ${escapeHtmlGlobal(source.source)}</span>
                            ${source.searchType ? `<span><i class="fa-solid fa-bolt"></i> ${escapeHtmlGlobal(source.searchType)}</span>` : ''}
                        </div>
                    </div>
                    <div class="evidence-actions">
                        ${source.canJump ? `
                            <button class="reader-open-btn" onclick="openPdfSource('${escapeHtmlGlobal(source.paperId)}', ${source.pageStart})" title="打开原文页">
                                <i class="fa-solid fa-book-open-reader"></i>
                            </button>` : ''}
                    </div>
                </article>`).join('')}`;
    }

    async function lookupEvidence() {
        if (!evidenceInput || !evidenceResults) return;
        const query = evidenceInput.value.trim();
        if (!query) return;

        evidenceLookupBtn.disabled = true;
        evidenceLookupBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> 正在找出处';
        evidenceResults.classList.remove('hidden');
        evidenceResults.innerHTML = '<div class="recent-placeholder">正在检索本地资料库...</div>';

        try {
            const res = await fetch(`/api/search/chunks?q=${encodeURIComponent(query)}&search_type=hybrid&top_k=8`);
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || '找出处失败');
            renderEvidenceResults(data.results || []);
        } catch (error) {
            evidenceResults.innerHTML = `<div class="recent-placeholder error">${escapeHtmlGlobal(error.message)}</div>`;
        } finally {
            evidenceLookupBtn.disabled = false;
            evidenceLookupBtn.innerHTML = '<i class="fa-solid fa-magnifying-glass-location"></i> 查找出处';
        }
    }

    if (evidenceLookupBtn) {
        evidenceLookupBtn.addEventListener('click', lookupEvidence);
    }
    if (evidenceInput) {
        evidenceInput.addEventListener('keydown', (event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                lookupEvidence();
            }
        });
    }

    function clearReaderCanvas() {
        const context = pdfCanvas.getContext('2d');
        context.clearRect(0, 0, pdfCanvas.width, pdfCanvas.height);
    }

    function highlightReaderChunks() {
        if (!readerChunks) return;
        readerChunks.querySelectorAll('.reader-chunk').forEach(btn => {
            const start = Number(btn.dataset.pageStart || btn.dataset.page || 1);
            const end = Number(btn.dataset.pageEnd || start);
            btn.classList.toggle('active', readerState.pageNum >= start && readerState.pageNum <= end);
        });
    }

    function resetReaderState() {
        readerState.paperId = null;
        readerState.paper = null;
        readerState.pdfDoc = null;
        readerState.pageNum = 1;
        readerState.scale = 1.2;
        readerState.rendering = false;
        readerState.renderError = null;
        readerState.pendingPage = null;
        readerState.chunks = [];
        readerState.pageTextCache = {};
        clearReaderCanvas();
        updateReaderControls();
        resetReaderEvidence();
        resetReaderTranslation();
    }

    function resetReaderEvidence() {
        if (readerEvidenceInput) readerEvidenceInput.value = '';
        if (readerEvidenceResults) {
            readerEvidenceResults.innerHTML = '<p class="reader-empty">输入观点后，结果会显示原文片段和页码。</p>';
        }
        if (readerEvidenceBtn) {
            readerEvidenceBtn.disabled = false;
            readerEvidenceBtn.innerHTML = '<i class="fa-solid fa-magnifying-glass-location"></i> 查找证据';
        }
        const currentScope = document.querySelector('input[name="readerEvidenceScope"][value="current"]');
        if (currentScope) currentScope.checked = true;
    }

    function renderReaderEvidenceResults(items) {
        if (!readerEvidenceResults) return;
        const sources = (items || []).slice(0, 8).map(normalizeSourceItem);
        if (!sources.length) {
            readerEvidenceResults.innerHTML = '<p class="reader-empty">没有找到可用证据。可以切换到“全部资料库”再试。</p>';
            return;
        }

        readerEvidenceResults.innerHTML = sources.map((source, index) => {
            const isCurrentPaper = source.paperId && source.paperId === readerState.paperId;
            const jumpLabel = isCurrentPaper ? '跳到本页' : '打开原文';
            return `
                <button class="reader-evidence-card" data-paper-id="${escapeHtmlGlobal(source.paperId)}" data-page="${source.pageStart}" ${source.canJump ? '' : 'disabled'}>
                    <span class="reader-evidence-rank">${index + 1}</span>
                    <span class="reader-evidence-body">
                        <strong>${escapeHtmlGlobal(source.title)}</strong>
                        <em>${escapeHtmlGlobal(source.pageLabelZh)}</em>
                        <small>${escapeHtmlGlobal(source.snippet || '暂无原文片段。')}</small>
                    </span>
                    <span class="reader-evidence-jump">${source.canJump ? jumpLabel : '无法跳转'}</span>
                </button>`;
        }).join('');
    }

    async function lookupReaderEvidence() {
        if (!readerEvidenceInput || !readerEvidenceBtn || !readerEvidenceResults) return;
        const query = readerEvidenceInput.value.trim();
        if (!query) return;

        const scope = document.querySelector('input[name="readerEvidenceScope"]:checked')?.value || 'current';
        const params = new URLSearchParams({
            q: query,
            search_type: 'hybrid',
            top_k: '8'
        });
        if (scope === 'current' && readerState.paperId) {
            params.set('paper_id', readerState.paperId);
        }

        readerEvidenceBtn.disabled = true;
        readerEvidenceBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> 正在查找';
        readerEvidenceResults.innerHTML = '<p class="reader-empty">正在检索原文片段...</p>';

        try {
            const res = await fetch(`/api/search/chunks?${params.toString()}`);
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || '查找证据失败');
            renderReaderEvidenceResults(data.results || []);
        } catch (error) {
            readerEvidenceResults.innerHTML = `<p class="reader-empty">${escapeHtmlGlobal(error.message)}</p>`;
        } finally {
            readerEvidenceBtn.disabled = false;
            readerEvidenceBtn.innerHTML = '<i class="fa-solid fa-magnifying-glass-location"></i> 查找证据';
        }
    }

    function setReaderTranslationStatus(message = '', isError = false) {
        if (!readerTranslateStatus) return;
        readerTranslateStatus.textContent = message;
        readerTranslateStatus.classList.toggle('error', Boolean(isError));
    }

    function resetReaderTranslation() {
        readerState.lastTranslateSource = '';
        if (readerTranslateSource) readerTranslateSource.value = '';
        if (readerTranslateResult) readerTranslateResult.textContent = '翻译结果会显示在这里。';
        if (readerRetryTranslateBtn) readerRetryTranslateBtn.classList.add('hidden');
        setReaderTranslationStatus('');
        if (readerTranslateBtn) {
            readerTranslateBtn.disabled = false;
            readerTranslateBtn.innerHTML = '<i class="fa-solid fa-language"></i> 翻译';
        }
    }

    async function getCurrentPageText() {
        if (!readerState.pdfDoc) throw new Error('No PDF is loaded.');
        const pageNum = readerState.pageNum || 1;
        if (readerState.pageTextCache[pageNum]) return readerState.pageTextCache[pageNum];

        const page = await readerState.pdfDoc.getPage(pageNum);
        const textContent = await page.getTextContent();
        const text = (textContent.items || [])
            .map(item => item.str || '')
            .join(' ')
            .replace(/\s+/g, ' ')
            .trim();
        readerState.pageTextCache[pageNum] = text;
        return text;
    }

    async function fillReaderTranslationFromPage() {
        if (!readerTranslateSource || !readerUsePageTextBtn) return;
        readerUsePageTextBtn.disabled = true;
        setReaderTranslationStatus('正在读取当前页文本...');
        try {
            const text = await getCurrentPageText();
            if (!text) throw new Error('当前页没有可提取文本，可能是扫描版 PDF。');
            readerTranslateSource.value = text.slice(0, 12000);
            setReaderTranslationStatus(text.length > 12000 ? '已填入当前页前 12000 字符。' : '已填入当前页文本。');
        } catch (error) {
            setReaderTranslationStatus(error.message, true);
        } finally {
            readerUsePageTextBtn.disabled = false;
        }
    }

    async function translateReaderText(sourceOverride = null) {
        if (!readerTranslateSource || !readerTranslateResult || !readerTranslateBtn) return;
        const sourceText = (sourceOverride || readerTranslateSource.value || '').trim();
        if (!sourceText) {
            setReaderTranslationStatus('请先输入或填入要翻译的原文。', true);
            return;
        }

        readerState.lastTranslateSource = sourceText;
        readerTranslateBtn.disabled = true;
        readerTranslateBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> 翻译中';
        if (readerRetryTranslateBtn) readerRetryTranslateBtn.classList.add('hidden');
        readerTranslateResult.textContent = '正在翻译...';
        setReaderTranslationStatus('');

        try {
            const res = await fetch('/api/translate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    text: sourceText,
                    source_language: 'auto',
                    target_language: 'zh-CN'
                })
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || '翻译失败');
            readerTranslateResult.textContent = data.translated_text || '';
            setReaderTranslationStatus(`已完成 · ${data.model || 'translator'}`);
        } catch (error) {
            readerTranslateResult.textContent = '翻译失败。';
            setReaderTranslationStatus(error.message, true);
            if (readerRetryTranslateBtn) readerRetryTranslateBtn.classList.remove('hidden');
        } finally {
            readerTranslateBtn.disabled = false;
            readerTranslateBtn.innerHTML = '<i class="fa-solid fa-language"></i> 翻译';
        }
    }

    async function renderPdfPage(pageNum) {
        if (!readerState.pdfDoc || readerState.rendering) {
            readerState.pendingPage = pageNum;
            return;
        }
        readerState.rendering = true;
        readerState.renderError = null;
        updateReaderControls();
        try {
            const page = await readerState.pdfDoc.getPage(pageNum);
            const viewport = page.getViewport({ scale: readerState.scale });
            const context = pdfCanvas.getContext('2d');
            pdfCanvas.width = Math.floor(viewport.width);
            pdfCanvas.height = Math.floor(viewport.height);
            clearReaderCanvas();
            await page.render({ canvasContext: context, viewport }).promise;
        } catch (error) {
            console.error('PDF page render failed:', error);
            readerState.renderError = `Page render failed: ${error.message}`;
        } finally {
            readerState.rendering = false;
            updateReaderControls();
        }
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
        const requestedPage = parseInt(pageNum, 10);
        readerState.pageNum = Math.min(Math.max(Number.isFinite(requestedPage) ? requestedPage : 1, 1), total);
        readerState.renderError = null;
        updateReaderControls();
        await renderPdfPage(readerState.pageNum);
    }

    async function loadReaderChunks(paperId) {
        readerState.chunks = [];
        if (readerChunks) readerChunks.innerHTML = '';
        try {
            const res = await fetch(`/api/papers/${paperId}/chunks?limit=200`);
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Failed to load chunks');
            const chunks = data.chunks || [];
            readerState.chunks = chunks;
            if (!chunks.length) {
                return;
            }
            readerChunks.innerHTML = chunks.map(chunk => `
                <span class="reader-chunk" data-page="${chunk.page_start || 1}" data-page-start="${chunk.page_start || 1}" data-page-end="${chunk.page_end || chunk.page_start || 1}"></span>
            `).join('');
            highlightReaderChunks();
        } catch (error) {
            console.warn('Failed to load reader chunks:', error);
            readerState.chunks = [];
        }
    }

    window.openPdfReader = async (paperId, page = 1) => {
        if (window.event) window.event.stopPropagation();
        if (!window.pdfjsLib) {
            alert('PDF.js failed to load. Check your network connection.');
            return;
        }
        const targetPage = Math.max(parseInt(page, 10) || 1, 1);
        if (readerState.pdfDoc && readerState.paperId === paperId) {
            showView('reader', false);
            await queuePdfPage(targetPage);
            return;
        }
        readerState.returnView = document.querySelector('.view-section:not(.hidden)')?.id?.replace('view-', '') || 'search';
        showView('reader', false);
        readerTitle.textContent = 'Loading PDF...';
        readerStatus.textContent = 'Preparing reader';
        if (readerChunks) readerChunks.innerHTML = '';
        resetReaderState();
        readerTitle.textContent = 'Loading PDF...';
        readerStatus.textContent = 'Preparing reader';

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
            readerStatus.textContent = 'Downloading PDF';
            readerState.pdfDoc = await pdfjsLib.getDocument({ url: pdfUrl }).promise;
            updateReaderControls();
            await queuePdfPage(targetPage);
            await loadReaderChunks(paperId);
        } catch (error) {
            resetReaderState();
            readerTitle.textContent = 'PDF Reader';
            readerStatus.textContent = 'Failed to load PDF';
            if (readerChunks) readerChunks.innerHTML = '';
        }
    };

    window.openPdfSource = async (paperId, page = 1, options = {}) => {
        if (!paperId) return;
        if (options.closeChat) closeChatPanel();
        await window.openPdfReader(paperId, page);
    };

    document.getElementById('readerBackBtn').addEventListener('click', () => {
        showView(readerState.returnView || 'search');
    });
    readerPrevBtn.addEventListener('click', () => queuePdfPage(readerState.pageNum - 1));
    readerNextBtn.addEventListener('click', () => queuePdfPage(readerState.pageNum + 1));
    readerZoomOutBtn.addEventListener('click', () => {
        readerState.scale = Math.max(0.6, readerState.scale - 0.2);
        queuePdfPage(readerState.pageNum);
    });
    readerZoomInBtn.addEventListener('click', () => {
        readerState.scale = Math.min(2.4, readerState.scale + 0.2);
        queuePdfPage(readerState.pageNum);
    });
    readerPageInput.addEventListener('change', () => queuePdfPage(Number(readerPageInput.value)));
    readerPageInput.addEventListener('keydown', (event) => {
        if (event.key === 'Enter') {
            event.preventDefault();
            readerPageInput.blur();
            queuePdfPage(Number(readerPageInput.value));
        }
    });
    if (readerEvidenceBtn) {
        readerEvidenceBtn.addEventListener('click', lookupReaderEvidence);
    }
    if (readerEvidenceInput) {
        readerEvidenceInput.addEventListener('keydown', (event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                lookupReaderEvidence();
            }
        });
    }
    if (readerEvidenceResults) {
        readerEvidenceResults.addEventListener('click', (event) => {
            const card = event.target.closest('.reader-evidence-card[data-paper-id]');
            if (!card) return;
            event.preventDefault();
            const paperId = card.dataset.paperId;
            const page = Number(card.dataset.page || 1);
            if (paperId === readerState.paperId) {
                queuePdfPage(page);
            } else {
                window.openPdfReader(paperId, page);
            }
        });
    }
    if (readerUsePageTextBtn) {
        readerUsePageTextBtn.addEventListener('click', fillReaderTranslationFromPage);
    }
    if (readerTranslateBtn) {
        readerTranslateBtn.addEventListener('click', () => translateReaderText());
    }
    if (readerRetryTranslateBtn) {
        readerRetryTranslateBtn.addEventListener('click', () => translateReaderText(readerState.lastTranslateSource));
    }
    updateReaderControls();

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
        const files = Array.from(fileInput.files || []);

        if (!files.length) {
            alert('请选择 PDF 文件');
            return;
        }

        const formData = new FormData();
        files.forEach(file => formData.append('files', file));
        formData.append('title', document.getElementById('pdfTitle').value.trim());
        formData.append('authors', document.getElementById('pdfAuthors').value.trim());
        formData.append('keywords', document.getElementById('pdfKeywords').value.trim());

        btn.disabled = true;
        btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> 正在导入 ${files.length} 篇...`;

        try {
            const res = await fetch('/api/papers/upload-pdfs', {
                method: 'POST',
                body: formData
            });
            const data = await res.json();
            if (!res.ok) {
                throw new Error(data.detail || '导入失败');
            }

            const resultRows = (data.results || []).map(item => `
                <div class="import-result-item ${item.success ? 'success' : 'failed'}">
                    <div>
                        <strong>${escapeHtmlGlobal(item.title || item.filename || '未命名 PDF')}</strong>
                        <p>${item.success
                            ? `页数：${item.pages} · 全文片段：${item.chunks} · 文本字数：${item.text_chars || 0} · 状态：${escapeHtmlGlobal(item.parse_status || 'unknown')}`
                            : `失败原因：${escapeHtmlGlobal(item.error || '未知错误')}`}</p>
                        ${item.success && item.quality_warnings && item.quality_warnings.length ? `
                            <div class="quality-warning">
                                <i class="fa-solid fa-triangle-exclamation"></i>
                                ${escapeHtmlGlobal(item.quality_warnings.join('；'))}
                            </div>` : ''}
                    </div>
                    ${item.success ? `<button class="reader-open-btn" onclick="openPdfReader('${escapeHtmlGlobal(item.paper_id)}')" title="打开原文"><i class="fa-solid fa-book-open-reader"></i></button>` : ''}
                </div>
            `).join('');

            logsDiv.innerHTML = `
                <div class="import-result-card">
                    <div class="import-result-summary">
                        <span><i class="fa-solid fa-file-import"></i> 批量导入完成</span>
                        <small>成功 ${data.succeeded || 0} 篇，失败 ${data.failed || 0} 篇</small>
                    </div>
                    <div class="import-result-list">
                        ${resultRows || '<p class="recent-placeholder">没有返回导入结果。</p>'}
                    </div>
                </div>
            ` + logsDiv.innerHTML;

            fileInput.value = '';
            document.getElementById('pdfTitle').value = '';
            document.getElementById('pdfAuthors').value = '';
            document.getElementById('pdfKeywords').value = '';
            loadRecentPdfs();
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
    let chatTypingRunId = 0;

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

    function renderInlineMarkdown(text) {
        const codeSpans = [];
        let html = escapeHtmlGlobal(text).replace(/`([^`]+)`/g, (_, code) => {
            const token = `@@CODE_SPAN_${codeSpans.length}@@`;
            codeSpans.push(`<code>${code}</code>`);
            return token;
        });
        html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
        codeSpans.forEach((code, index) => {
            html = html.replace(`@@CODE_SPAN_${index}@@`, code);
        });
        return html;
    }

    function flushMarkdownParagraph(parts, output) {
        if (!parts.length) return;
        output.push(`<p>${parts.map(renderInlineMarkdown).join('<br>')}</p>`);
        parts.length = 0;
    }

    function flushMarkdownList(listState, output) {
        if (!listState.items.length) return;
        output.push(`<${listState.type}>${listState.items.map(item => `<li>${renderInlineMarkdown(item)}</li>`).join('')}</${listState.type}>`);
        listState.items = [];
        listState.type = null;
    }

    function parseSimpleMarkdown(text) {
        if (!text) return '';
        const lines = String(text).replace(/\r\n/g, '\n').split('\n');
        const output = [];
        const paragraph = [];
        const listState = { type: null, items: [] };
        let inCodeBlock = false;
        let codeLanguage = '';
        let codeLines = [];

        const flushBlocks = () => {
            flushMarkdownParagraph(paragraph, output);
            flushMarkdownList(listState, output);
        };

        lines.forEach(line => {
            const fence = line.match(/^```(\w+)?\s*$/);
            if (fence) {
                if (inCodeBlock) {
                    output.push(`<pre><code${codeLanguage ? ` data-language="${escapeHtmlGlobal(codeLanguage)}"` : ''}>${escapeHtmlGlobal(codeLines.join('\n'))}</code></pre>`);
                    inCodeBlock = false;
                    codeLanguage = '';
                    codeLines = [];
                } else {
                    flushBlocks();
                    inCodeBlock = true;
                    codeLanguage = fence[1] || '';
                    codeLines = [];
                }
                return;
            }

            if (inCodeBlock) {
                codeLines.push(line);
                return;
            }

            if (!line.trim()) {
                flushBlocks();
                return;
            }

            const heading = line.match(/^(#{1,3})\s+(.+)$/);
            if (heading) {
                flushBlocks();
                const level = Math.min(heading[1].length + 2, 5);
                output.push(`<h${level}>${renderInlineMarkdown(heading[2].trim())}</h${level}>`);
                return;
            }

            const quote = line.match(/^>\s?(.*)$/);
            if (quote) {
                flushBlocks();
                output.push(`<blockquote>${renderInlineMarkdown(quote[1])}</blockquote>`);
                return;
            }

            const unordered = line.match(/^\s*[-*+]\s+(.+)$/);
            const ordered = line.match(/^\s*\d+\.\s+(.+)$/);
            if (unordered || ordered) {
                flushMarkdownParagraph(paragraph, output);
                const type = unordered ? 'ul' : 'ol';
                if (listState.type && listState.type !== type) {
                    flushMarkdownList(listState, output);
                }
                listState.type = type;
                listState.items.push((unordered || ordered)[1].trim());
                return;
            }

            flushMarkdownList(listState, output);
            paragraph.push(line);
        });

        if (inCodeBlock) {
            output.push(`<pre><code${codeLanguage ? ` data-language="${escapeHtmlGlobal(codeLanguage)}"` : ''}>${escapeHtmlGlobal(codeLines.join('\n'))}</code></pre>`);
        }
        flushBlocks();
        return output.join('');
    }


    function renderSourceCards(sources) {
        if (!sources || !sources.length) return '';
        const cards = sources.map((source, index) => {
            const item = normalizeSourceItem(source);
            return `
                <button class="source-card${item.canJump ? '' : ' disabled'}" ${item.canJump ? `data-paper-id="${escapeHtmlGlobal(item.paperId)}" data-page="${item.pageStart}"` : 'disabled'}>
                    <span class="source-index">${index + 1}</span>
                    <span class="source-body">
                        <strong>${escapeHtmlGlobal(item.title)}</strong>
                        <em>${escapeHtmlGlobal(item.pageLabel)}</em>
                        ${item.snippet ? `<small>${escapeHtmlGlobal(item.snippet)}</small>` : ''}
                    </span>
                    ${item.canJump ? '<i class="fa-solid fa-arrow-up-right-from-square"></i>' : ''}
                </button>`;
        }).join('');
        return `<div class="source-card-list">${cards}</div>`;
    }

    function isNearChatBottom(threshold = 72) {
        return chatHistory.scrollHeight - chatHistory.scrollTop - chatHistory.clientHeight <= threshold;
    }

    function scrollToBottom() {
        chatHistory.scrollTop = chatHistory.scrollHeight;
    }

    function maybeScrollToBottom(shouldFollow) {
        if (shouldFollow) scrollToBottom();
    }

    function startAssistantTyping(contentEl, msg, runId) {
        const fullText = msg.content || '';
        const sourceHtml = renderSourceCards(msg.sources);
        const chunkSize = fullText.length > 900 ? 5 : 2;
        let offset = 0;

        function renderFrame() {
            if (runId !== chatTypingRunId) return;
            const shouldFollow = isNearChatBottom();
            offset = Math.min(offset + chunkSize, fullText.length);
            contentEl.innerHTML = parseSimpleMarkdown(fullText.slice(0, offset));

            if (offset >= fullText.length) {
                contentEl.innerHTML = `${parseSimpleMarkdown(fullText)}${sourceHtml}`;
                maybeScrollToBottom(shouldFollow);
                return;
            }

            maybeScrollToBottom(shouldFollow);
            window.setTimeout(renderFrame, 14);
        }

        renderFrame();
    }

    // 渲染聊天记录
    function renderChatMessages(options = {}) {
        chatTypingRunId += 1;
        const typingRunId = chatTypingRunId;
        const shouldFollow = options.forceScroll || isNearChatBottom();
        const lastAssistantIndex = options.animateLastAssistant
            ? currentChatMessages.map(msg => msg.role).lastIndexOf('assistant')
            : -1;

        // 清空除了初始欢迎语之外的全部气泡
        const initialWelcome = chatHistory.firstElementChild;
        chatHistory.innerHTML = '';
        if (initialWelcome) chatHistory.appendChild(initialWelcome);

        currentChatMessages.forEach((msg, index) => {
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
                    const toolNames = msg.tool_calls.map(tc => (tc.function && tc.function.name) || 'tool').join(', ');
                    bubble.innerHTML = `
                        <div class="tool-content">
                            <i class="fa-solid fa-wrench"></i>
                            <span>Agent 正在调用内部工具: ${escapeHtmlGlobal(toolNames)}...</span>
                        </div>
                    `;
                } else if (msg.content) {
                    // 正常的助手回复
                    bubble.classList.add('assistant-bubble');
                    const content = document.createElement('div');
                    content.classList.add('bubble-content');
                    bubble.appendChild(content);
                    if (options.animateLastAssistant && index === lastAssistantIndex) {
                        content.innerHTML = '';
                        chatHistory.appendChild(bubble);
                        maybeScrollToBottom(shouldFollow);
                        startAssistantTyping(content, msg, typingRunId);
                        return;
                    }
                    content.innerHTML = `${parseSimpleMarkdown(msg.content)}${renderSourceCards(msg.sources)}`;
                } else {
                    return; // 防止空状态
                }
            } else if (msg.role === 'tool') {
                bubble.classList.add('tool-bubble');
                bubble.innerHTML = `
                    <div class="tool-content" style="border-color: #10b981;">
                        <i class="fa-solid fa-check" style="color: #10b981;"></i>
                        <span>工具 [${escapeHtmlGlobal(msg.name)}] 执行完毕</span>
                    </div>
                `;
            }
            chatHistory.appendChild(bubble);
        });
        maybeScrollToBottom(shouldFollow);
    }

    // 发送消息
    chatHistory.addEventListener('click', (event) => {
        const sourceBtn = event.target.closest('.source-card[data-paper-id]');
        if (!sourceBtn) return;
        event.preventDefault();
        window.openPdfSource(sourceBtn.dataset.paperId, Number(sourceBtn.dataset.page || 1), { closeChat: true });
    });
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
        const shouldFollowLoading = isNearChatBottom();
        chatHistory.appendChild(loadingBubble);
        maybeScrollToBottom(shouldFollowLoading);

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
            renderChatMessages({ animateLastAssistant: true }); // 重新渲染最终状态（移除 loading 气泡）
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

    loadRecentPdfs();

});
