const db = require('./db');

exports.reserve = async (items) => {
  // UPDATE inventory SET qty = qty - $1 WHERE sku = $2 AND qty >= $1
  const results = await Promise.all(items.map(i => db.query('reserve', i)));
  return results.every(r => r.rowCount === 1);
};
