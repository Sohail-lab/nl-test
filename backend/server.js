const http = require('http');
const fs = require('fs');
const path = require('path');

const UPLOAD_DIR = path.join(__dirname, 'uploads');
if (!fs.existsSync(UPLOAD_DIR)) fs.mkdirSync(UPLOAD_DIR, { recursive: true });

const jobs = new Map();


let worker = null;
try {
    worker = require('./worker');
} catch (e) {
    worker = null;
}

const { spawnSync, spawn } = require('child_process');
function findPythonCommand() {
    const candidates = ['python', 'python3'];
    for (const cmd of candidates) {
        try {
            const r = spawnSync(cmd, ['--version'], { encoding: 'utf8' });
            if (r.status === 0 || (r.stdout && r.stdout.toLowerCase().includes('python'))) return cmd;
        } catch (e) {
            // ignore
        }
    }
    return null;
}

const PYTHON_CMD = findPythonCommand();
const PY_WORKER_PATH = path.join(__dirname, 'worker.py');
const HAS_PY_WORKER = fs.existsSync(PY_WORKER_PATH) && PYTHON_CMD !== null;

function bufferSplit(buffer, sep) {
    const parts = [];
    let start = 0;
    let idx = buffer.indexOf(sep, start);
    while (idx !== -1) {
        parts.push(buffer.slice(start, idx));
        start = idx + sep.length;
        idx = buffer.indexOf(sep, start);
    }
    parts.push(buffer.slice(start));
    return parts;
}

function parseMultipart(buffer, boundary) {
    const sep = Buffer.from('--' + boundary);
    const endSep = Buffer.from('--' + boundary + '--');
    const rawParts = bufferSplit(buffer, sep);
    const parts = [];

    rawParts.forEach((p) => {
        // skip empty and end marker
        if (!p || p.length === 0) return;
        if (p.indexOf(endSep) === 0) return;

        // remove leading CRLF if present
        if (p[0] === 13 && p[1] === 10) p = p.slice(2);

        const idx = p.indexOf(Buffer.from('\r\n\r\n'));
        if (idx === -1) return;
        const headerBuf = p.slice(0, idx).toString('utf8');
        let body = p.slice(idx + 4);

        // remove trailing CRLF
        if (body.length >= 2 && body[body.length - 2] === 13 && body[body.length - 1] === 10) {
            body = body.slice(0, body.length - 2);
        }

        const headers = {};
        headerBuf.split('\r\n').forEach((line) => {
            const idx2 = line.indexOf(':');
            if (idx2 !== -1) {
                const name = line.slice(0, idx2).trim().toLowerCase();
                const val = line.slice(idx2 + 1).trim();
                headers[name] = val;
            }
        });

        parts.push({ headers, body });
    });

    return parts;
}

function parseContentDisposition(disposition) {
    const result = {};
    const parts = disposition.split(';').map((p) => p.trim());
    parts.forEach((p) => {
        const eq = p.indexOf('=');
        if (eq === -1) {
            result.type = p;
        } else {
            const key = p.slice(0, eq).trim();
            let val = p.slice(eq + 1).trim();
            if (val.startsWith('"') && val.endsWith('"')) val = val.slice(1, -1);
            result[key] = val;
        }
    });
    return result;
}

function createJob(filePath, originalName, websiteUrl) {
    const id = `${Date.now()}-${Math.floor(Math.random() * 10000)}`;
    const job = {
        id,
        file: filePath,
        originalName,
        websiteUrl,
        status: 'pending',
        createdAt: new Date().toISOString(),
        result: null,
    };
    jobs.set(id, job);

    console.log('[BACKEND] Creating job:', { id, websiteUrl, pythonAvailable: HAS_PY_WORKER });

    // Prefer Python worker if available; otherwise fall back to JS worker or simulated processing
    if (HAS_PY_WORKER) {
        job.status = 'running';
        const args = [PY_WORKER_PATH, filePath, id, websiteUrl || ''];
        console.log('[BACKEND] Spawning Python worker with args:', args);
        const proc = spawn(PYTHON_CMD, args, { stdio: ['ignore', 'pipe', 'pipe'] });

        // Capture and display stdout
        if (proc.stdout) {
            proc.stdout.on('data', (data) => {
                console.log(`[WORKER STDOUT] ${data.toString()}`);
            });
        }

        // Capture and display stderr
        if (proc.stderr) {
            proc.stderr.on('data', (data) => {
                console.error(`[WORKER STDERR] ${data.toString()}`);
            });
        }

        proc.on('exit', (code) => {
            const resultPath = path.join(UPLOAD_DIR, `${id}.result.json`);
            if (fs.existsSync(resultPath)) {
                try {
                    const data = JSON.parse(fs.readFileSync(resultPath, 'utf8'));
                    job.status = data && data.success ? 'completed' : 'failed';
                    job.result = data;
                } catch (e) {
                    job.status = code === 0 ? 'completed' : 'failed';
                    job.result = { success: code === 0, error: e && String(e) };
                }
            } else {
                job.status = code === 0 ? 'completed' : 'failed';
                job.result = { success: code === 0, note: 'No result file created' };
            }
        });
        proc.on('error', (err) => {
            job.status = 'failed';
            job.result = { success: false, error: String(err) };
        });
    } else if (worker && typeof worker.process === 'function') {
        // run in next tick to avoid blocking
        process.nextTick(async () => {
            try {
                job.status = 'running';
                const r = await worker.process(filePath, id);
                job.status = 'completed';
                job.result = r;
            } catch (e) {
                job.status = 'failed';
                job.result = { success: false, error: String(e) };
            }
        });
    } else {
        // Simulate async processing. Replace this with real worker.
        setTimeout(() => {
            job.status = 'running';
            // fake processing delay
            setTimeout(() => {
                job.status = 'completed';
                job.result = {
                    success: true,
                    notes: 'This is a placeholder result. Install dependencies and enable the worker to process the Excel and run steps on target URLs.',
                };
                // persist result to disk for later retrieval
                try {
                    fs.writeFileSync(path.join(UPLOAD_DIR, `${id}.result.json`), JSON.stringify(job.result, null, 2));
                } catch (e) { }
            }, 2000);
        }, 1000);
    }

    return job;
}

const server = http.createServer((req, res) => {
    // Basic CORS for local dev
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET,POST,OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

    if (req.method === 'OPTIONS') {
        res.writeHead(204);
        res.end();
        return;
    }

    if (req.method === 'POST' && req.url === '/upload-test') {
        const contentType = req.headers['content-type'] || '';
        const match = contentType.match(/multipart\/form-data; boundary=(.+)/);
        if (!match) {
            res.writeHead(400, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ error: 'Expected multipart/form-data' }));
            return;
        }

        const boundary = match[1];
        const chunks = [];
        req.on('data', (chunk) => chunks.push(chunk));
        req.on('end', () => {
            const buffer = Buffer.concat(chunks);
            const parts = parseMultipart(buffer, boundary);
            let savedFile = null;
            let websiteUrl = '';

            for (const p of parts) {
                const cd = p.headers['content-disposition'];
                if (!cd) continue;
                const info = parseContentDisposition(cd);

                // Extract testFile
                if (info.name === 'testFile' && info.filename) {
                    const filename = `${Date.now()}-${info.filename}`.replace(/[^a-zA-Z0-9._-]/g, '_');
                    const filePath = path.join(UPLOAD_DIR, filename);
                    fs.writeFileSync(filePath, p.body);
                    savedFile = { path: filePath, filename: info.filename };
                    console.log('[BACKEND] Saved file:', filePath);
                }

                // Extract websiteUrl
                if (info.name === 'websiteUrl') {
                    websiteUrl = p.body.toString('utf8').trim();
                    console.log('[BACKEND] Received websiteUrl:', websiteUrl);
                    console.log('[BACKEND] websiteUrl length:', websiteUrl.length);
                    console.log('[BACKEND] websiteUrl bool:', !!websiteUrl);
                }
            }

            if (!savedFile) {
                res.writeHead(400, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ error: 'No file field "testFile" found' }));
                return;
            }

            const job = createJob(savedFile.path, savedFile.filename, websiteUrl);
            res.writeHead(200, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ jobId: job.id }));
        });
        req.on('error', (err) => {
            res.writeHead(500, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ error: 'Upload failed', details: String(err) }));
        });

        return;
    }

    if (req.method === 'GET' && req.url.startsWith('/jobs/')) {
        const id = req.url.split('/')[2];
        if (!jobs.has(id)) {
            res.writeHead(404, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ error: 'Job not found' }));
            return;
        }
        const job = jobs.get(id);
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ id: job.id, status: job.status, createdAt: job.createdAt, originalName: job.originalName }));
        return;
    }

    if (req.method === 'GET' && req.url.startsWith('/jobs-result/')) {
        const id = req.url.split('/')[2];
        const resultPath = path.join(UPLOAD_DIR, `${id}.result.json`);
        if (!fs.existsSync(resultPath)) {
            res.writeHead(404, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ error: 'Result not ready' }));
            return;
        }
        const data = fs.readFileSync(resultPath, 'utf8');
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(data);
        return;
    }

    if (req.method === 'GET' && req.url.startsWith('/jobs-progress/')) {
        const id = req.url.split('/')[2];
        const progressPath = path.join(UPLOAD_DIR, `${id}.progress.json`);
        if (!fs.existsSync(progressPath)) {
            res.writeHead(200, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ currentStep: 0, totalSteps: 0, completedSteps: [], failedSteps: [] }));
            return;
        }
        const data = fs.readFileSync(progressPath, 'utf8');
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(data);
        return;
    }

    if (req.method === 'POST' && req.url.startsWith('/jobs-stop/')) {
        const id = req.url.split('/')[2];
        if (!jobs.has(id)) {
            res.writeHead(404, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ error: 'Job not found' }));
            return;
        }

        // Create a stop file signal
        const stopPath = path.join(UPLOAD_DIR, `.${id}.stop`);
        try {
            fs.writeFileSync(stopPath, 'stop', 'utf8');
            console.log(`[BACKEND] Stop signal created for job ${id}`);
        } catch (e) {
            console.error(`[BACKEND] Error creating stop signal: ${e}`);
        }

        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ success: true, message: 'Stop signal sent' }));
        return;
    }

    if (req.method === "GET" && req.url === "/reports") {
        try {
            const uploadsDir = path.join(__dirname, "uploads");

            const files = fs.readdirSync(uploadsDir)
                .filter(file => file.endsWith(".result.json"));

            const reports = [];

            for (const file of files) {
                try {
                    const filePath = path.join(uploadsDir, file);
                    const content = JSON.parse(fs.readFileSync(filePath, "utf8"));

                    // Skip invalid files
                    if (!content) continue;

                    reports.push({
                        fileName: file,
                        jobId: content.jobId || file.replace(".result.json", ""),
                        parsed: content.parsed || [],
                        executed: content.executed || [],
                        success: content.success ?? false
                    });

                } catch (err) {
                    console.log("Skipping bad report:", file);
                }
            }

            res.writeHead(200, { "Content-Type": "application/json" });
            res.end(JSON.stringify(reports));

        } catch (err) {
            res.writeHead(500, { "Content-Type": "application/json" });
            res.end(JSON.stringify({ error: "Failed to read reports" }));
        }

        return;
    }

    // not found
    res.writeHead(404, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ error: 'Not found' }));
});


const PORT = process.env.PORT || 4000;
server.listen(PORT, () => {
    console.log(`Backend server listening on http://localhost:${PORT}`);
});
