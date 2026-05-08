/**
 * Verdicto API Client
 * Central abstraction layer for all backend API calls.
 * All components use this — never raw fetch() scattered across files.
 */

const API_BASE = import.meta.env.VITE_API_URL ?? '/api/v1';

class APIError extends Error {
  constructor(message, code, queryId) {
    super(message);
    this.code = code;
    this.queryId = queryId;
    this.name = 'APIError';
  }
}

async function request(endpoint, options = {}) {
  const url = `${API_BASE}${endpoint}`;
  const config = {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  };

  try {
    const response = await fetch(url, config);

    if (!response.ok) {
      let errorData;
      try {
        errorData = await response.json();
      } catch {
        errorData = { error: { code: 'UNKNOWN', message: response.statusText } };
      }
      const err = errorData?.error || errorData;
      throw new APIError(
        err.message || 'Request failed',
        err.code || 'UNKNOWN',
        err.query_id
      );
    }

    return await response.json();
  } catch (error) {
    if (error instanceof APIError) throw error;
    throw new APIError(
      error.message || 'Network error — is the backend running?',
      'NETWORK_ERROR'
    );
  }
}

// ── Query Endpoints ────────────────────────────────────────────────────

/**
 * Submit a legal query for multi-agent analysis.
 * @param {{ query: string, filters?: object, options?: object }} params
 * @returns {Promise<object>} QueryResponse
 */
export async function queryLegalCases({ query, filters = {}, options = {} }) {
  return request('/query', {
    method: 'POST',
    body: JSON.stringify({ query, filters, options }),
  });
}

/**
 * Poll the status of a running query.
 * @param {string} queryId
 * @returns {Promise<object>} QueryStatusResponse
 */
export async function getQueryStatus(queryId) {
  return request(`/query/${queryId}/status`);
}

/**
 * Get the full details of a completed query.
 * @param {string} queryId
 * @returns {Promise<object>} QueryResponse
 */
export async function getQuery(queryId) {
  return request(`/query/${queryId}`);
}

/**
 * List past query records.
 * @param {{ limit?: number, offset?: number }} params
 * @returns {Promise<{ queries: object[], total: number }>}
 */
export async function listQueries({ limit = 50, offset = 0 } = {}) {
  return request(`/queries?limit=${limit}&offset=${offset}`);
}

// ── Case Endpoints ─────────────────────────────────────────────────────

/**
 * Get full details of a single case.
 * @param {string} caseId
 * @returns {Promise<object>} CaseDetailResponse
 */
export async function getCaseDetails(caseId) {
  return request(`/cases/${caseId}`);
}

/**
 * Get cases similar to a given case.
 * @param {string} caseId
 * @param {number} topK
 * @returns {Promise<object[]>} SimilarCaseResponse[]
 */
export async function getSimilarCases(caseId, topK = 10) {
  return request(`/cases/${caseId}/similar?top_k=${topK}`);
}

/**
 * Extract text from an uploaded document (PDF/TXT).
 * @param {File} file 
 * @returns {Promise<{ filename: string, text: string }>}
 */
export async function extractFileText(file) {
  const formData = new FormData();
  formData.append('file', file);
  
  try {
    const response = await fetch(`${API_BASE}/cases/extract`, {
      method: 'POST',
      body: formData,
    });
    
    if (!response.ok) {
      const err = await response.json();
      throw new Error(err.detail || 'File extraction failed');
    }
    return await response.json();
  } catch (error) {
    throw new Error(error.message || 'Network error during extraction');
  }
}


// ── System Endpoints ───────────────────────────────────────────────────

/**
 * Get system statistics.
 * @returns {Promise<object>} SystemStatsResponse
 */
export async function getSystemStats() {
  return request('/stats');
}

/**
 * Health check for all services.
 * @returns {Promise<object>} HealthResponse
 */
export async function getHealthStatus() {
  return request('/health');
}

export { APIError, API_BASE };
