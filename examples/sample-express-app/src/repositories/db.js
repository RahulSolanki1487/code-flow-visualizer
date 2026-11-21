// Stub database client for the demo
exports.query = async (name, params) => ({ rowCount: 1, rows: [{ id: 'ord_1', ...params }] });
