import React, { useState } from 'react';
import ProductCard from './ProductCard';

function App() {
  // Sinov uchun mahsulotlar ro'yxati
  const [products] = useState([
    {
      id: 1,
      name: 'Akril burchak oshxona mebeli',
      dimensions: '4m x 2m',
      material: 'Yuqori porloq akril',
      price: '8500000',
      imageUrl: 'https://images.unsplash.com/photo-1556911220-e15b29be8c8f?auto=format&fit=crop&w=600&q=80'
    },
    {
      id: 2,
      name: 'Zamonaviy yotoqxona to‘plami',
      dimensions: '5m x 4m',
      material: 'MDF va Laminat',
      price: '6200000',
      imageUrl: 'https://images.unsplash.com/photo-1616594039964-ae9021a400a0?auto=format&fit=crop&w=600&q=80'
    }
  ]);

  const handleBuy = (product) => {
    alert(Siz tanlagan mahsulot: ${product.name}. Buyurtmani rasmiylashtirish uchun botga qayting!);
  };

  return (
    <div style={{ padding: '20px', fontFamily: 'Arial, sans-serif', backgroundColor: '#f9f9f9', minHeight: '100vh' }}>
      <h1 style={{ textAlign: 'center', color: '#333' }}>Mebelix - Buyurtma berish</h1>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '15px' }}>
        {products.map((product) => (
          <ProductCard key={product.id} product={product} onBuy={handleBuy} />
        ))}
      </div>
    </div>
  );
}

export default App;
