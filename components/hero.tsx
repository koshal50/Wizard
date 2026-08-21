'use client';

import { useState, useEffect } from 'react';
import { X } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { GodRays, MeshGradient } from '@paper-design/shaders-react';

export default function Hero() {
	const [isExpanded, setIsExpanded] = useState(false);

	const handleExpand = () => {
		setIsExpanded(true);
	};

	const handleClose = () => {
		setIsExpanded(false);
	};

	useEffect(() => {
		if (isExpanded) {
			document.body.style.overflow = 'hidden';
		} else {
			document.body.style.overflow = 'unset';
		}
	}, [isExpanded]);

	return (
		<>
			<div className="relative flex min-h-screen flex-col items-center justify-center px-4 sm:px-6 py-12 sm:py-20">
				{/* GodRays Background */}
				<div className="absolute inset-0">
					<GodRays
						colorBack="#00000000"
						colors={['#FFFFFF6E', '#F3F3F3F0', '#8A8A8A', '#989898']}
						colorBloom="#FFFFFF"
						offsetX={0.85}
						offsetY={-1}
						intensity={1}
						spotty={0.45}
						midSize={10}
						midIntensity={0}
						density={0.12}
						bloom={0.15}
						speed={1}
						scale={1.6}
						frame={3332042.8159981333}
						style={{
							height: '100%',
							width: '100%',
							position: 'absolute',
							top: 0,
							left: 0,
						}}
					/>
				</div>

				<div className="relative z-10 flex flex-col items-center gap-4 sm:gap-6 text-center">
					<h1 className="text-4xl sm:text-5xl md:text-6xl lg:text-7xl font-normal leading-[90%] tracking-[-0.03em] text-black mix-blend-exclusion max-w-2xl">
						Accelerate your marketing pipeline
					</h1>

					<p className="text-base sm:text-lg md:text-xl leading-[160%] text-black max-w-2xl px-4">
						Empower your team to focus on creation, not configuration. Build,
						launch, and grow exceptional digital products with confidence and
						speed.
					</p>

					<AnimatePresence initial={false}>
						{!isExpanded && (
							<motion.div className="inline-block relative">
								<motion.div
									style={{
										borderRadius: '100px',
									}}
									layout
									layoutId="cta-card"
									className="absolute inset-0 bg-[#004FE5] items-center justify-center transform-gpu will-change-transform"
								></motion.div>
								<motion.button
									initial={{ opacity: 0, scale: 0.8 }}
									animate={{ opacity: 1, scale: 1 }}
									transition={{ delay: 0.2 }}
									exit={{ opacity: 0, scale: 0.8 }}
									layout={false}
									onClick={handleExpand}
									className="h-15 px-6 sm:px-8 py-3 text-lg sm:text-xl font-regular text-[#E3E3E3] tracking-[-0.01em] relative"
								>
									Request a demo
								</motion.button>
							</motion.div>
						)}
					</AnimatePresence>
				</div>
			</div>

			<AnimatePresence initial={false}>
				{isExpanded && (
					<div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-2">
						<motion.div
							layoutId="cta-card"
							style={{
								borderRadius: '24px',
							}}
							layout
							className="relative flex h-full w-full overflow-hidden bg-[#004FE5] transform-gpu will-change-transform"
						>
							<div className="h-full w-full overflow-y-auto scrollbar-hide">
								<motion.div
									initial={{ opacity: 0 }}
									animate={{ opacity: 1 }}
									className="relative py-8 z-10 min-h-full flex flex-col lg:flex-row w-full max-w-[1100px] mx-auto items-center p-6 sm:p-10 lg:p-16 gap-8 lg:gap-16"
								>
									<div className="flex-1 flex flex-col justify-center space-y-3 w-full">
										<h2 className="text-3xl sm:text-4xl lg:text-5xl font-medium text-white leading-none tracking-[-0.03em]">
											Talk to our sales team
										</h2>

										<div className="space-y-4 sm:space-y-6 pt-4">
											<div className="flex gap-3 sm:gap-4">
												<div className="flex-shrink-0 w-10 h-10 sm:w-12 sm:h-12 rounded-lg bg-white/10 flex items-center justify-center">
													<svg
														className="w-5 h-5 sm:w-6 sm:h-6 text-white"
														fill="none"
														viewBox="0 0 24 24"
														stroke="currentColor"
													>
														<path
															strokeLinecap="round"
															strokeLinejoin="round"
															strokeWidth={2}
															d="M5 13l4 4L19 7"
														/>
													</svg>
												</div>
												<div>
													<p className="text-sm sm:text-base text-white leading-[150%]">
														Learn how Acme can transform your business with
														tailored solutions and flexible pricing options.
													</p>
												</div>
											</div>
											<div className="flex gap-3 sm:gap-4">
												<div className="flex-shrink-0 w-10 h-10 sm:w-12 sm:h-12 rounded-lg bg-white/10 flex items-center justify-center">
													<svg
														className="w-5 h-5 sm:w-6 sm:h-6 text-white"
														fill="none"
														viewBox="0 0 24 24"
														stroke="currentColor"
													>
														<path
															strokeLinecap="round"
															strokeLinejoin="round"
															strokeWidth={2}
															d="M13 10V3L4 14h7v7l9-11h-7z"
														/>
													</svg>
												</div>
												<div>
													<p className="text-sm sm:text-base text-white leading-[150%]">
														Experience firsthand how Acme Platform accelerates
														delivery &amp; drives results.
													</p>
												</div>
											</div>
										</div>

										<div className="pt-6 sm:pt-8 mt-6 sm:mt-8 border-t border-white/20">
											<p className="text-lg sm:text-xl lg:text-2xl text-white leading-[150%] mb-4">
												Acme empowers our team to move faster and ship products
												with confidence.
											</p>
											<div className="flex items-center gap-3 sm:gap-4">
												<img
													src="/professional-headshot.png"
													alt="Sarah Chen"
													className="w-10 h-10 sm:w-12 sm:h-12 rounded-full object-cover"
												/>
												<div>
													<p className="text-base sm:text-lg lg:text-xl text-white">
														Sarah Chen
													</p>
													<p className="text-sm sm:text-base text-white/70">
														{'Chrono'}
													</p>
												</div>
											</div>
										</div>
									</div>

									<div className="flex-1 w-full">
										<form className="space-y-4 sm:space-y-5">
											{/* Name Field */}
											<div>
												<label
													htmlFor="name"
													className="block text-[10px] font-mono font-normal text-white mb-2 tracking-[0.5px] uppercase"
												>
													FULL NAME *
												</label>
												<input
													type="text"
													id="name"
													name="name"
													className="w-full px-4 py-2.5 rounded-lg bg-[#001F63] border-0 text-white placeholder:text-white/50 focus:outline-none focus:ring-2 focus:ring-white/20 transition-all text-sm h-10"
												/>
											</div>

											{/* Work Email Field */}
											<div>
												<label
													htmlFor="email"
													className="block text-[10px] font-mono font-normal text-white mb-2 tracking-[0.5px] uppercase"
												>
													WORK EMAIL *
												</label>
												<input
													type="email"
													id="email"
													name="phone"
													className="w-full px-4 py-2.5 rounded-lg bg-[#001F63] border-0 text-white placeholder:text-white/50 focus:outline-none focus:ring-2 focus:ring-white/20 transition-all text-sm h-10"
												/>
											</div>

											<div className="flex flex-col sm:flex-row gap-4">
												<div className="flex-1">
													<label
														htmlFor="website"
														className="block text-[10px] font-mono font-normal text-white mb-2 tracking-[0.5px] uppercase"
													>
														COMPANY WEBSITE
													</label>
													<input
														type="url"
														id="website"
														name="website"
														className="w-full px-4 py-2.5 rounded-lg bg-[#001F63] border-0 text-white placeholder:text-white/50 focus:outline-none focus:ring-2 focus:ring-white/20 transition-all text-sm h-10"
													/>
												</div>
												<div className="sm:w-32 w-full">
													<label
														htmlFor="company-size"
														className="block text-[10px] font-mono font-normal text-white mb-2 tracking-[0.5px] uppercase"
													>
														COMPANY SIZE
													</label>
													<select
														id="company-size"
														name="company-size"
														className="w-full px-4 py-2.5 rounded-lg bg-[#001F63] border-0 text-white focus:outline-none focus:ring-2 focus:ring-white/20 transition-all appearance-none cursor-pointer text-sm h-10"
														style={{
															backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='white' strokeWidth='2' strokeLinecap='round' strokeLinejoin='round'%3E%3Cpolyline points='6 9 12 15 18 9'%3E%3C/polyline%3E%3C/svg%3E")`,
															backgroundRepeat: 'no-repeat',
															backgroundPosition: 'right 0.75rem center',
															backgroundSize: '1rem',
														}}
													>
														<option value="1-10">1-10</option>
														<option value="11-50">11-50</option>
														<option value="51-200">51-200</option>
														<option value="201-500">201-500</option>
														<option value="501+">501+</option>
													</select>
												</div>
											</div>

											{/* Message Field */}
											<div>
												<label
													htmlFor="message"
													className="block text-[10px] font-mono font-normal text-white mb-2 tracking-[0.5px] uppercase"
												>
													ANYTHING ELSE?
												</label>
												<textarea
													id="message"
													name="message"
													rows={3}
													className="w-full px-4 py-3 rounded-lg bg-[#001F63] border-0 text-white placeholder:text-white/50 focus:outline-none focus:ring-2 focus:ring-white/20 transition-all resize-none text-sm"
												/>
											</div>

											{/* Submit Button */}
											<button
												type="submit"
												className="w-full px-8 py-2.5 rounded-full bg-white text-[#0041C1] font-medium hover:bg-white/90 transition-colors tracking-[-0.03em] h-10"
											>
												Submit
											</button>
										</form>
									</div>
								</motion.div>
							</div>
							<motion.div
								initial={{ opacity: 0, scale: 2 }}
								animate={{ opacity: 1, scale: 1 }}
								exit={{ opacity: 0 }}
								layout={false}
								transition={{ duration: 0.15, delay: 0.05 }}
								className="absolute h-full inset-0 overflow-hidden pointer-events-none"
								style={{
									borderRadius: '24px',
								}}
							>
								<MeshGradient
									speed={1}
									colors={['#2452F1', '#022474', '#163DB9', '#0B1D99']}
									distortion={0.8}
									swirl={0.1}
									grainMixer={0}
									grainOverlay={0}
									className="inset-0 sticky top-0"
									style={{ height: '100%', width: '100%' }}
								/>
							</motion.div>

							{/* Close Button */}
							<motion.button
								onClick={handleClose}
								className="absolute right-6 top-6 z-10 flex h-10 w-10 items-center justify-center text-white bg-transparent transition-colors hover:bg-white/10 rounded-full"
								aria-label="Close"
							>
								<X className="h-5 w-5" />
							</motion.button>
						</motion.div>
					</div>
				)}
			</AnimatePresence>
		</>
	);
}
