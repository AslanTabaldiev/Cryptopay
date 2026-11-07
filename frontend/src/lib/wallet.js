// Работа с кошельком MetaMask через стандарты EIP-1193 (API провайдера)
// и EIP-6963 (обнаружение кошельков). SDK MetaMask не нужен.

const METAMASK_RDNS = "io.metamask";

const SEPOLIA_PARAMS = {
  chainId: "0xaa36a7",
  chainName: "Sepolia",
  nativeCurrency: { name: "Sepolia Ether", symbol: "ETH", decimals: 18 },
  rpcUrls: ["https://ethereum-sepolia-rpc.publicnode.com"],
  blockExplorerUrls: ["https://sepolia.etherscan.io"],
};

export const METAMASK_DOWNLOAD_URL = "https://metamask.io/download/";

// ---------- обнаружение MetaMask ----------
let announced = null; // провайдер, который MetaMask объявил через EIP-6963
const listeners = new Set();

if (typeof window !== "undefined") {
  window.addEventListener("eip6963:announceProvider", (event) => {
    if (event.detail?.info?.rdns === METAMASK_RDNS) {
      announced = event.detail.provider;
      listeners.forEach((cb) => cb());
    }
  });
  window.dispatchEvent(new Event("eip6963:requestProvider"));
}

/** Провайдер MetaMask или undefined, если расширение не установлено. */
export function getMetaMask() {
  if (announced) return announced;
  if (typeof window === "undefined" || !window.ethereum) return undefined;
  const { ethereum } = window;
  // несколько расширений сразу: MetaMask лежит в ethereum.providers
  const fromList = ethereum.providers?.find((p) => p.isMetaMask);
  if (fromList) return fromList;
  return ethereum.isMetaMask ? ethereum : undefined;
}

/** Подписка на появление MetaMask (он может объявить себя чуть позже загрузки страницы). */
export function onMetaMaskDetected(callback) {
  listeners.add(callback);
  return () => listeners.delete(callback);
}

// ---------- действия ----------
function friendlyError(error) {
  if (error?.code === 4001) return new Error("Вы отклонили запрос в MetaMask.");
  if (error?.code === -32002) return new Error("В MetaMask уже есть открытый запрос. Откройте расширение, чтобы продолжить.");
  return new Error(error?.message || "Ошибка MetaMask");
}

function requireMetaMask() {
  const provider = getMetaMask();
  if (!provider) throw new Error("MetaMask не найден. Установите расширение MetaMask и перезагрузите страницу.");
  return provider;
}

export async function connectWallet() {
  const provider = requireMetaMask();
  try {
    const [account] = await provider.request({ method: "eth_requestAccounts" });
    return account;
  } catch (error) {
    throw friendlyError(error);
  }
}

export async function ensureChain(chainId) {
  const provider = requireMetaMask();
  const target = "0x" + Number(chainId).toString(16);
  const current = await provider.request({ method: "eth_chainId" });
  if (current?.toLowerCase() === target) return;
  try {
    await provider.request({ method: "wallet_switchEthereumChain", params: [{ chainId: target }] });
  } catch (error) {
    // 4902 — сеть ещё не добавлена в MetaMask
    if (error?.code === 4902 && target === SEPOLIA_PARAMS.chainId) {
      await provider.request({ method: "wallet_addEthereumChain", params: [SEPOLIA_PARAMS] });
      return;
    }
    throw friendlyError(error);
  }
}

export async function sendPayment({ from, to, valueWei }) {
  const provider = requireMetaMask();
  try {
    return await provider.request({
      method: "eth_sendTransaction",
      params: [{ from, to, value: "0x" + BigInt(valueWei).toString(16) }],
    });
  } catch (error) {
    throw friendlyError(error);
  }
}

export function shortAddress(address) {
  return address ? `${address.slice(0, 6)}…${address.slice(-4)}` : "";
}
