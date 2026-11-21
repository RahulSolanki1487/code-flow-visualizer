module.exports = function auth(req, res, next) {
  const token = req.headers.authorization;
  if (!token) {
    return res.status(401).json({ error: 'unauthorized' });
  }
  req.user = { id: token.replace('Bearer ', '') };
  next();
};
