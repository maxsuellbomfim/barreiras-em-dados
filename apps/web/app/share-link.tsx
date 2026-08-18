const BASE_URL = "https://barreiras-em-dados.vercel.app";

/**
 * Link de compartilhamento via WhatsApp — o canal cívico dominante na cidade.
 * Sem JavaScript: âncora simples para wa.me com texto e URL pré-preenchidos.
 */
export default function ShareLink({
  path,
  message,
}: Readonly<{ path: string; message: string }>) {
  const text = encodeURIComponent(`${message} ${BASE_URL}${path}`);
  return (
    <a
      className="share-whatsapp"
      href={`https://wa.me/?text=${text}`}
      rel="noreferrer"
      target="_blank"
    >
      Compartilhar no WhatsApp
    </a>
  );
}
