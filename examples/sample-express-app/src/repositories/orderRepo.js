const db = require('./db');

exports.save = async (order) => {
  const { rows } = await db.query('insert_order', order);
  return rows[0];
};

exports.findById = async (id) => {
  const { rows } = await db.query('find_order', { id });
  return rows[0];
};
