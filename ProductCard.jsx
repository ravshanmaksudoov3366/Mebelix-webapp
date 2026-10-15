import React from 'react';

const ProductCard = ({ product, onBuy }) => {
    return (
        <div style={styles.card}>
            <img src={product.imageUrl} alt={product.name} style={styles.image} />
            <h2 style={styles.title}>{product.name}</h2>
            <p style={styles.text}><strong>O'lchamlari:</strong> {product.dimensions}</p>
            <p style={styles.text}><strong>Material:</strong> {product.material}</p>
            <p style={styles.price}><strong>Narxi:</strong> {product.price} So'm</p>
            <p style={styles.delivery}>🚚 Yetkazib berish va o'rnatish: 3-7 kun ichida</p>
            <button style={styles.button} onClick={() => onBuy(product)}>
                Sotib olish
            </button>
        </div>
    );
};

const styles = {
    card: { border: '1px solid #ddd', borderRadius: '12px', padding: '16px', margin: '10px', backgroundColor: '#fff', boxShadow: '0 4px 6px rgba(0,0,0,0.1)' },
    image: { width: '100%', height: '200px', objectFit: 'cover', borderRadius: '8px' },
    title: { fontSize: '20px', margin: '10px 0', color: '#333' },
    text: { margin: '4px 0', color: '#555' },
    price: { fontSize: '18px', color: '#2e7d32', margin: '8px 0' },
    delivery: { fontSize: '12px', color: '#888', fontStyle: 'italic' },
    button: { width: '100%', padding: '10px', backgroundColor: '#0088cc', color: '#fff', border: 'none', borderRadius: '8px', cursor: 'pointer', fontWeight: 'bold' }
};

export default ProductCard;
